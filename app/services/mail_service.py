# app/services/mail_service.py
import os
import shutil
import time
import uuid
import smtplib
import email
from email.header import Header, decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional, Tuple
from app.config import MAILDIR_PATH, SMTP_HOST, SMTP_PORT, SMTP_FROM

class MailService:
    @staticmethod
    def get_maildir_path() -> str:
        path = MAILDIR_PATH
        try:
            os.makedirs(os.path.join(path, "new"), exist_ok=True)
            os.makedirs(os.path.join(path, "cur"), exist_ok=True)
            os.makedirs(os.path.join(path, "tmp"), exist_ok=True)
            os.makedirs(os.path.join(path, "sent", "new"), exist_ok=True)
            os.makedirs(os.path.join(path, "sent", "cur"), exist_ok=True)
            os.makedirs(os.path.join(path, "trash", "new"), exist_ok=True)
            os.makedirs(os.path.join(path, "trash", "cur"), exist_ok=True)
            return path
        except Exception:
            fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "maildir")
            os.makedirs(os.path.join(fallback, "new"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "cur"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "tmp"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "sent", "new"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "sent", "cur"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "trash", "new"), exist_ok=True)
            os.makedirs(os.path.join(fallback, "trash", "cur"), exist_ok=True)
            return fallback

    @staticmethod
    def decode_mime_header(header_value: Optional[str]) -> str:
        if not header_value:
            return ""
        try:
            fragments = decode_header(header_value)
            decoded_parts = []
            for fragment, encoding in fragments:
                if isinstance(fragment, bytes):
                    decoded_parts.append(fragment.decode(encoding or "utf-8", errors="replace"))
                else:
                    decoded_parts.append(str(fragment))
            return "".join(decoded_parts)
        except Exception:
            return str(header_value)

    @staticmethod
    def extract_body(msg: email.message.Message) -> Tuple[str, str]:
        body_text = ""
        body_html = ""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition:
                        continue
                    if content_type == "text/plain" and not body_text:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace") if payload else ""
                    elif content_type == "text/html" and not body_html:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body_html = payload.decode(charset, errors="replace") if payload else ""
            else:
                content_type = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace") if payload else ""
                if content_type == "text/html":
                    body_html = decoded
                else:
                    body_text = decoded
        except Exception:
            body_text = str(msg.get_payload() or "")

        return body_text, body_html

    @classmethod
    def list_folder_messages(cls, folder: str = "inbox") -> List[Dict]:
        base = cls.get_maildir_path()
        results = []

        if folder == "inbox":
            dirs = [(os.path.join(base, "new"), True), (os.path.join(base, "cur"), False)]
        elif folder == "sent":
            dirs = [(os.path.join(base, "sent", "cur"), False), (os.path.join(base, "sent", "new"), False)]
        elif folder == "trash":
            dirs = [(os.path.join(base, "trash", "cur"), False), (os.path.join(base, "trash", "new"), False)]
        else:
            dirs = []

        for directory, is_new in dirs:
            if not os.path.exists(directory):
                continue
            for fname in os.listdir(directory):
                full_path = os.path.join(directory, fname)
                if not os.path.isfile(full_path):
                    continue
                try:
                    stat = os.stat(full_path)
                    with open(full_path, "rb") as f:
                        msg = email.message_from_binary_file(f)

                    subject = cls.decode_mime_header(msg.get("Subject"))
                    from_addr = cls.decode_mime_header(msg.get("From"))
                    to_addr = cls.decode_mime_header(msg.get("To"))
                    date_header = cls.decode_mime_header(msg.get("Date"))

                    body_text, _ = cls.extract_body(msg)
                    snippet = body_text.strip().replace("\n", " ")[:120] if body_text else ""

                    is_seen = (":2," in fname and "S" in fname.split(":2,")[-1]) if not is_new else False
                    is_unread = is_new or (not is_seen)

                    results.append({
                        "id": fname,
                        "folder": folder,
                        "file_path": full_path,
                        "subject": subject or "(No Subject)",
                        "from": from_addr or "Unknown Sender",
                        "to": to_addr or "",
                        "date": date_header or time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                        "timestamp": stat.st_mtime,
                        "is_unread": is_unread,
                        "snippet": snippet
                    })
                except Exception:
                    continue

        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    @classmethod
    def get_unread_count(cls) -> int:
        base = cls.get_maildir_path()
        new_dir = os.path.join(base, "new")
        if not os.path.exists(new_dir):
            return 0
        try:
            return len([f for f in os.listdir(new_dir) if os.path.isfile(os.path.join(new_dir, f))])
        except Exception:
            return 0

    @classmethod
    def read_message(cls, folder: str, msg_id: str) -> Optional[Dict]:
        base = cls.get_maildir_path()
        target_path = None
        is_in_new = False

        search_dirs = []
        if folder == "inbox":
            search_dirs = [os.path.join(base, "new"), os.path.join(base, "cur")]
        elif folder == "sent":
            search_dirs = [os.path.join(base, "sent", "cur"), os.path.join(base, "sent", "new")]
        elif folder == "trash":
            search_dirs = [os.path.join(base, "trash", "cur"), os.path.join(base, "trash", "new")]

        for sdir in search_dirs:
            p = os.path.join(sdir, msg_id)
            if os.path.isfile(p):
                target_path = p
                is_in_new = ("new" in sdir)
                break

        if not target_path:
            return None

        with open(target_path, "rb") as f:
            msg = email.message_from_binary_file(f)

        subject = cls.decode_mime_header(msg.get("Subject"))
        from_addr = cls.decode_mime_header(msg.get("From"))
        to_addr = cls.decode_mime_header(msg.get("To"))
        date_header = cls.decode_mime_header(msg.get("Date"))
        body_text, body_html = cls.extract_body(msg)

        # Mark as read: if located in 'new', move to 'cur' with Seen flag
        if folder == "inbox" and is_in_new:
            try:
                clean_id = msg_id.split(":2,")[0]
                cur_filename = f"{clean_id}:2,S"
                cur_dest = os.path.join(base, "cur", cur_filename)
                shutil.move(target_path, cur_dest)
                msg_id = cur_filename
            except Exception:
                pass

        return {
            "id": msg_id,
            "folder": folder,
            "subject": subject or "(No Subject)",
            "from": from_addr or "Unknown",
            "to": to_addr or "",
            "date": date_header or "",
            "body_text": body_text,
            "body_html": body_html
        }

    @classmethod
    def move_to_trash(cls, folder: str, msg_id: str) -> bool:
        base = cls.get_maildir_path()
        search_dirs = []
        if folder == "inbox":
            search_dirs = [os.path.join(base, "new"), os.path.join(base, "cur")]
        elif folder == "sent":
            search_dirs = [os.path.join(base, "sent", "cur"), os.path.join(base, "sent", "new")]
        elif folder == "trash":
            # If already in trash, delete permanently
            search_dirs = [os.path.join(base, "trash", "cur"), os.path.join(base, "trash", "new")]
            for sdir in search_dirs:
                p = os.path.join(sdir, msg_id)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                        return True
                    except Exception:
                        return False
            return False

        for sdir in search_dirs:
            p = os.path.join(sdir, msg_id)
            if os.path.isfile(p):
                trash_dest = os.path.join(base, "trash", "cur", msg_id)
                try:
                    shutil.move(p, trash_dest)
                    return True
                except Exception:
                    return False

        return False

    @classmethod
    def empty_trash(cls) -> int:
        base = cls.get_maildir_path()
        count = 0
        for sdir in [os.path.join(base, "trash", "cur"), os.path.join(base, "trash", "new")]:
            if not os.path.exists(sdir):
                continue
            for fname in os.listdir(sdir):
                fp = os.path.join(sdir, fname)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                        count += 1
                    except Exception:
                        pass
        return count

    @classmethod
    def send_email(cls, to_address: str, subject: str, body_text: str, reply_to_id: Optional[str] = None) -> bool:
        base = cls.get_maildir_path()
        from_address = SMTP_FROM

        msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = from_address
        msg["To"] = to_address
        if reply_to_id:
            msg["In-Reply-To"] = reply_to_id
            msg["References"] = reply_to_id

        # Send via SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.send_message(msg)

        # Record into sent/cur
        try:
            sent_dir = os.path.join(base, "sent", "cur")
            os.makedirs(sent_dir, exist_ok=True)
            sent_filename = f"{int(time.time())}.{uuid.uuid4().hex[:8]}.kaalk:2,S"
            sent_path = os.path.join(sent_dir, sent_filename)
            with open(sent_path, "wb") as f:
                f.write(msg.as_bytes())
        except Exception:
            pass

        return True