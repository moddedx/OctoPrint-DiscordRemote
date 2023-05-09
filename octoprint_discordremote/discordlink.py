import os
import socket
import subprocess
import threading
import time

from . import Command
from .proto.messages_pb2 import Response, Request, Presence


class DiscordLink:
    process = None
    client = None
    command: Command

    def __init__(self, bot_token, channel_id, command: Command):
        self.lock = threading.Lock()
        self.command = command

        self.bot_token = bot_token
        self.channel_id = channel_id

        self.listener_thread = threading.Thread(target=self.listener)
        self.listener_thread.start()

        self.start_discord()

    def start_discord(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.settimeout(10)
        server.bind(('127.0.0.1', 0))
        sock_details = server.getsockname()
        server.listen()

        my_env = os.environ.copy()
        my_env["BOT_TOKEN"] = self.bot_token
        my_env["CHANNEL_ID"] = self.channel_id
        my_env["DISCORD_LINK_PORT"] = str(sock_details[1])
        self.process = subprocess.Popen(["python", "-m", "octoprint_discordshim"], env=my_env)

        while self.client is None:
            try:
                self.client, _ = server.accept()
                server.close()
            except socket.timeout:
                pass

    def shutdown_discord(self):
        if self.process:
            self.process.kill()
            self.process.wait()
            self.process = None
        if self.client:
            self.client.close()
            self.client = None

    def send(self, messages: Response):
        self.lock.acquire()
        cmdproto = messages.SerializeToString()
        try:
            self.client.send(len(cmdproto).to_bytes(length=4, byteorder='little'))
            self.client.send(cmdproto)
        except:
            pass
        self.lock.release()

    def update_precence(self, status):
        resp = Response(presence=Presence(presence=status))
        self.send(resp)

    def listener(self):
        while True:
            while self.client is None:
                time.sleep(1)

            try:
                length_bytes = self.client.recv(4)
                if len(length_bytes) == 0:
                    return  # Socket has closed.
                length = int.from_bytes(length_bytes, byteorder='little')

                data_bytes = self.client.recv(length)
                data = Request()
                data.ParseFromString(data_bytes)

                if data.command:
                    messages = self.command.parse_command(data.command)
                    self.send(messages=messages)
            except TimeoutError:
                continue
            except Exception as e:
                self.shutdown_discord()
                time.sleep(5000)
                self.start_discord()
