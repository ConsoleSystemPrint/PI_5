import configparser
import socket
import ssl
import base64
import os
import mimetypes
from email.utils import formatdate
from email.header import Header

def read_config(file_path):
    config = configparser.ConfigParser()
    config.read(file_path)
    return config

class SMTPClient:
    def __init__(self, server, port, username, password):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.sock = None
        self.ssl_context = ssl.create_default_context()

    def connect(self):
        try:
            self.sock = self.ssl_context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=self.server)
            self.sock.connect((self.server, self.port))
            self._get_response()
        except Exception as e:
            raise ConnectionError(f"Не удалось подключиться: {e}")

    def _send_command(self, command, expect_code):
        try:
            self.sock.sendall(command.encode() + b'\r\n')
            return self._get_response(expect_code)
        except Exception as e:
            raise RuntimeError(f"Не удалось отправить команду '{command}': {e}")

    def _get_response(self, expect_code=None):
        response = b""
        while True:
            part = self.sock.recv(1024)
            response += part
            if len(part) < 1024:
                break
        response_str = response.decode()
        if expect_code and not response_str.startswith(str(expect_code)):
            raise Exception(f"Ожидаемый {expect_code}, получил {response_str}")
        return response_str

    def login(self):
        self._send_command(f"HELO {self.server}", 250)
        self._send_command("AUTH LOGIN", 334)
        self._send_command(base64.b64encode(self.username.encode()).decode(), 334)
        self._send_command(base64.b64encode(self.password.encode()).decode(), 235)

    def send_mail(self, from_addr, to_addrs, subject, body, attachments):
        boundary = "BOUNDARY_123456789"
        self._send_command(f"MAIL FROM:<{from_addr}>", 250)
        for addr in to_addrs.split(","):
            self._send_command(f"RCPT TO:<{addr.strip()}>", 250)
        self._send_command("DATA", 354)

        message = f"From: {from_addr}\r\nTo: {to_addrs}\r\nSubject: {Header(subject, 'utf-8')}\r\n"
        message += f"Date: {formatdate(localtime=True)}\r\n"
        message += "MIME-Version: 1.0\r\n"
        message += f"Content-Type: multipart/mixed; boundary={boundary}\r\n\r\n"
        message += f"--{boundary}\r\n"
        message += "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        with open(body, 'r') as f:
            message += f.read()
        message += "\r\n"

        for attachment in attachments.split(","):
            if not attachment:
                continue
            file_path = attachment.strip()
            ctype, encoding = mimetypes.guess_type(file_path)
            if ctype is None or encoding is None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)

            with open(file_path, 'rb') as f:
                file_data = f.read()

            message += f"--{boundary}\r\n"
            message += f"Content-Type: {ctype}; name={os.path.basename(file_path)}\r\n"
            message += "Content-Transfer-Encoding: base64\r\n"
            message += f"Content-Disposition: attachment; filename={os.path.basename(file_path)}\r\n\r\n"
            message += base64.b64encode(file_data).decode() + "\r\n"

        message += f"--{boundary}--\r\n."
        self._send_command(message, 250)

    def close(self):
        try:
            self._send_command("QUIT", 221)
            self.sock.close()
        except Exception as e:
            print(f"Не удалось закрыть соединение: {e}")

if __name__ == "__main__":
    config = read_config("config.ini")

    smtp_config = config['smtp']
    email_config = config['email']

    client = SMTPClient(
        smtp_config.get('server'),
        smtp_config.getint('port'),
        smtp_config.get('username'),
        smtp_config.get('password')
    )

    try:
        client.connect()
        client.login()
        client.send_mail(
            email_config.get('from'),
            email_config.get('to'),
            email_config.get('subject'),
            email_config.get('body_file'),
            email_config.get('attachments')
        )
        print("Письмо успешно отправлено")
    except Exception as e:
        print(f"Не удалось отправить письмо: {e}")
    finally:
        client.close()
