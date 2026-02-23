import smtplib
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cat.mad_hatter.decorators import tool

from .main import send_ws_notification, generate_email_subject, get_settings


# Funzioni di utility interna

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_email_input(data: dict) -> tuple[bool, str]:
    """
    Valida i campi obbligatori di un payload email.
    Restituisce (True, "") se valido, (False, messaggio_errore) altrimenti.
    """
    recipient = data.get("recipient", "").strip()
    body = data.get("body", "").strip()

    if not recipient:
        return False, "Errore: il campo 'recipient' è obbligatorio."
    if not EMAIL_REGEX.match(recipient):
        return False, f"Errore: l'indirizzo email '{recipient}' non è valido."
    if not body or len(body) < 10:
        return False, "Errore: il corpo del messaggio è troppo breve o vuoto (minimo 10 caratteri)."
    return True, ""


def parse_tool_input(tool_input: str) -> tuple[dict | None, str]:
    """
    Parsing dell'input JSON del tool.
    Restituisce (dati, "") oppure (None, messaggio_errore).
    """
    try:
        data = json.loads(tool_input)
        return data, ""
    except json.JSONDecodeError as e:
        return None, f"Errore: il formato JSON fornito non è valido. Dettaglio: {e}"


#  Tool anteprima mail

@tool(return_direct=True)
def preview_email(tool_input, cat):
    """
    Genera e mostra un'anteprima dell'email prima dell'invio effettivo.
    Permette all'utente di verificare destinatario, oggetto e corpo prima di confermare.
    L'input DEVE essere un JSON valido con questa struttura:
    {"recipient": "email@esempio.com", "subject": "Oggetto opzionale", "body": "Testo del messaggio"}
    Il campo 'subject' è facoltativo: se omesso viene generato automaticamente dall'AI.
    """
    data, error = parse_tool_input(tool_input)
    if data is None:
        send_ws_notification(cat, "Errore: formato dati non valido.", "error")
        return error

    valid, validation_error = validate_email_input(data)
    if not valid:
        send_ws_notification(cat, validation_error, "warning")
        return validation_error

    recipient = data["recipient"].strip()
    body = data["body"].strip()
    subject = data.get("subject", "").strip()
    auto_note = ""

    if not subject:
        subject = generate_email_subject(body, cat)
        auto_note = " (generato automaticamente dall'AI)"

    preview_message = (
        f"ANTEPRIMA EMAIL\n"
        f"{'━' * 40}\n"
        f"Destinatario : {recipient}\n"
        f"Oggetto      : {subject}{auto_note}\n"
        f"{'━' * 40}\n\n"
        f"{body}\n\n"
        f"{'━' * 40}"
    )

    send_ws_notification(cat, preview_message, "info")
    return (
        f"Anteprima generata e mostrata.\n"
        f"Destinatario: {recipient}\n"
        f"Oggetto: {subject}{auto_note}\n\n"
        f"Conferma l'invio per procedere."
    )

#  Tool invio mail

@tool(return_direct=True)
def send_email(tool_input, cat):
    """
    Esegue l'invio effettivo dell'email tramite protocollo SMTP.
    Usare SOLO dopo aver mostrato l'anteprima con 'preview_email' e ottenuto conferma dall'utente.
    L'input DEVE essere un JSON valido con questa struttura:
    {"recipient": "email@esempio.com", "subject": "Oggetto confermato", "body": "Testo del messaggio"}
    Assicurati di includere sempre nel campo 'subject' l'oggetto esatto che è stato mostrato e approvato nell'anteprima, per evitare che venga generato da zero.
    """
    send_ws_notification(cat, "Preparazione invio in corso...", "info")

    data, error = parse_tool_input(tool_input)
    if data is None:
        send_ws_notification(cat, "Errore: formato dati non valido.", "error")
        return error

    valid, validation_error = validate_email_input(data)
    if not valid:
        send_ws_notification(cat, validation_error, "warning")
        return validation_error

    recipient = data["recipient"].strip()
    body = data["body"].strip()
    subject = data.get("subject", "").strip()

    if not subject:
        subject = generate_email_subject(body, cat)

    settings = get_settings(cat)

    if not settings.sender_email or not settings.sender_password:
        send_ws_notification(cat, "Errore: credenziali non configurate.", "error")
        return "Errore di configurazione: le credenziali SMTP non sono impostate. Vai in Admin → Plugin → Email Assistant."

    try:
        msg = MIMEMultipart()
        msg['From'] = settings.sender_email
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        send_ws_notification(cat, f"Connessione a {settings.smtp_server}:{settings.smtp_port}...", "info")

        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.sender_email, settings.sender_password)
            server.sendmail(settings.sender_email, recipient, msg.as_string())

        success_msg = f"✓ Email inviata con successo a {recipient}"
        send_ws_notification(cat, success_msg, "success")
        return (
            f"Operazione completata con successo.\n"
            f"Destinatario: {recipient}\n"
            f"Oggetto: {subject}"
        )

    except smtplib.SMTPAuthenticationError:
        err = "Errore di autenticazione SMTP: verifica email e password nelle impostazioni."
        send_ws_notification(cat, err, "error")
        return err
    except smtplib.SMTPException as e:
        err = f"Errore SMTP: {e}"
        send_ws_notification(cat, err, "error")
        print(f"[EmailAssistant] {err}")
        return err
    except Exception as e:
        err = f"Errore imprevisto durante l'invio: {e}"
        send_ws_notification(cat, err, "error")
        print(f"[EmailAssistant] {err}")
        return err