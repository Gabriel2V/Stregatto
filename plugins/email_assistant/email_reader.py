import imaplib
import email
import json
from email.header import decode_header
from cat.mad_hatter.decorators import tool

from .main import send_ws_notification, get_settings


# Funzioni di utility interna

def get_email_body(msg) -> str:
    """
    Estrae il corpo testuale dell'email.
    Gestisce sia messaggi multipart che semplici.
    """
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception as e:
                    print(f"[EmailAssistant] Errore decodifica parte multipart: {e}")
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception as e:
            print(f"[EmailAssistant] Errore decodifica corpo email: {e}")
    return body


def decode_header_value(raw_value: str) -> str:
    """Decodifica un header email (es. Subject, From) in una stringa leggibile."""
    try:
        decoded, encoding = decode_header(raw_value)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(encoding if encoding else "utf-8", errors="replace")
        return decoded
    except Exception as e:
        print(f"[EmailAssistant] Errore decodifica header '{raw_value}': {e}")
        return raw_value


def connect_imap(settings):
    """Crea e restituisce una connessione IMAP autenticata."""
    mail = imaplib.IMAP4_SSL(settings.imap_server, settings.imap_port)
    mail.login(settings.sender_email, settings.sender_password)
    return mail


def fetch_email_summaries(mail, uids_to_process: list, preview_length: int) -> list:
    """
    Recupera i dati delle email per una lista di UID.
    Restituisce una lista di dizionari con mittente, oggetto e corpo troncato.
    """
    emails_data = []
    for uid in uids_to_process:
        try:
            res, msg_data = mail.uid('fetch', uid, '(BODY.PEEK[])')
            if res != 'OK':
                print(f"[EmailAssistant] Impossibile recuperare UID {uid}: status {res}")
                continue
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = decode_header_value(msg.get("Subject", "(nessun oggetto)"))
                    sender = decode_header_value(msg.get("From", "(mittente sconosciuto)"))
                    body = get_email_body(msg)
                    emails_data.append({
                        "uid": int(uid),
                        "sender": sender,
                        "subject": subject,
                        "body_preview": body[:preview_length]
                    })
        except Exception as e:
            print(f"[EmailAssistant] Errore elaborazione UID {uid}: {e}")
    return emails_data


def format_email_list(emails_data: list) -> str:
    """Formatta una lista di dizionari email in testo leggibile."""
    parts = []
    for e in emails_data:
        parts.append(
            f"Da: {e['sender']}\n"
            f"Oggetto: {e['subject']}\n"
            f"Messaggio:\n{e['body_preview']}..."
        )
    return "Nuove email trovate:\n\n" + "\n\n---\n\n".join(parts)


#  Tool di controllo nuove mail

@tool(return_direct=True)
def check_new_emails(tool_input, cat):
    """
    Controlla la presenza di nuove email nella casella di posta in arrivo.
    Non richiede alcun input specifico.
    Recupera le ultime email non ancora analizzate dall'ultimo controllo.
    """
    send_ws_notification(cat, "Controllo nuova posta in corso...", "info")

    settings = get_settings(cat)

    if not settings.sender_email or not settings.sender_password:
        return "Errore: credenziali IMAP non configurate. Vai in Admin → Plugin → Email Assistant."

    try:
        mail = connect_imap(settings)
        mail.select("inbox")

        status, messages = mail.uid('search', None, "ALL")
        if status != 'OK':
            mail.logout()
            return "Errore durante la ricerca delle email."

        uids = messages[0].split()
        if not uids:
            mail.logout()
            return "Nessuna email presente nella casella di posta."

        last_checked_uid = cat.working_memory.get("last_email_uid", 0)
        new_uids = [uid for uid in uids if int(uid) > last_checked_uid]

        if not new_uids:
            mail.logout()
            send_ws_notification(cat, "Nessuna nuova email trovata.", "info")
            return "Nessun nuovo messaggio dall'ultimo controllo."

        # Limite al numero configurato nelle impostazioni
        uids_to_process = new_uids[-settings.max_emails_to_fetch:]
        highest_uid = max(int(uid) for uid in uids_to_process)

        emails_data = fetch_email_summaries(
            mail, uids_to_process, settings.email_preview_length
        )

        cat.working_memory["last_email_uid"] = highest_uid
        mail.logout()

        if not emails_data:
            return "Nessuna email recuperata (possibile errore di decodifica)."

        send_ws_notification(cat, f"Trovate {len(emails_data)} nuove email.", "success")
        return format_email_list(emails_data)

    except imaplib.IMAP4.error as e:
        return f"Errore di autenticazione IMAP: {e}"
    except Exception as e:
        print(f"[EmailAssistant] Errore imprevisto check_new_emails: {e}")
        return f"Errore durante la connessione IMAP: {e}"


#  Tool filtro email per mittente

@tool
def filter_emails_by_sender(sender_filter, cat):
    """
    Cerca e mostra tutte le email nella casella di posta provenienti da uno specifico mittente.
    Input: indirizzo email o parte del nome/dominio del mittente da cercare.
    Esempio di input: 'mario.rossi@azienda.it' oppure 'azienda.it'
    """
    if not sender_filter or len(sender_filter.strip()) < 3:
        return "Errore: fornisci almeno 3 caratteri per filtrare il mittente."

    send_ws_notification(cat, f"Ricerca email da '{sender_filter}' in corso...", "info")

    settings = get_settings(cat)

    if not settings.sender_email or not settings.sender_password:
        return "Errore: credenziali IMAP non configurate. Vai in Admin → Plugin → Email Assistant."

    try:
        mail = connect_imap(settings)
        mail.select("inbox")

        # Ricerca IMAP per mittente (case-insensitive lato server)
        search_criterion = f'FROM "{sender_filter.strip()}"'
        status, messages = mail.uid('search', None, search_criterion)

        if status != 'OK':
            mail.logout()
            return f"Errore durante la ricerca per mittente '{sender_filter}'."

        uids = messages[0].split()
        if not uids:
            mail.logout()
            send_ws_notification(cat, "Nessuna email trovata per questo mittente.", "info")
            return f"Nessuna email trovata da '{sender_filter}'."

        # Recupera al massimo le ultime N email
        uids_to_process = uids[-settings.max_emails_to_fetch:]
        emails_data = fetch_email_summaries(
            mail, uids_to_process, settings.email_preview_length
        )
        mail.logout()

        if not emails_data:
            return f"Email trovate ma impossibile decodificarle da '{sender_filter}'."

        send_ws_notification(
            cat, f"Trovate {len(emails_data)} email da '{sender_filter}'.", "success"
        )

        parts = []
        for e in emails_data:
            parts.append(
                f"Da: {e['sender']}\n"
                f"Oggetto: {e['subject']}\n"
                f"Messaggio:\n{e['body_preview']}..."
            )
        return (
            f"Email da '{sender_filter}' ({len(emails_data)} trovate):\n\n"
            + "\n\n---\n\n".join(parts)
        )

    except imaplib.IMAP4.error as e:
        return f"Errore di autenticazione IMAP: {e}"
    except Exception as e:
        print(f"[EmailAssistant] Errore imprevisto filter_emails_by_sender: {e}")
        return f"Errore durante il filtro per mittente: {e}"