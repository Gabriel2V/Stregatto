import smtplib
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cat.mad_hatter.decorators import tool

from .main import send_ws_notification, generate_email_subject, get_settings
import email.utils

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
    Usa questo tool OGNI VOLTA che l'utente vuole scrivere, inviare, mandare, preparare o comporre una nuova email.
    Genera un'anteprima dell'email da mostrare all'utente prima dell'invio.
    Usare SEMPRE prima di send_email: non inviare mai senza aver mostrato l'anteprima.
    L'input DEVE essere un JSON valido con questa struttura:
    {"recipient": "email@esempio.com", "subject": "Oggetto opzionale", "body": "Testo del messaggio"}
    Il campo 'subject' è facoltativo: se omesso viene generato automaticamente dall'AI.
    Esempio: {"recipient": "mario@esempio.it", "body": "Ciao Mario, ti scrivo per..."}
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

    return (
        f"ANTEPRIMA EMAIL\n"
        f"{'━' * 40}\n"
        f"Destinatario : {recipient}\n"
        f"Oggetto      : {subject}{auto_note}\n"
        f"{'━' * 40}\n\n"
        f"{body}\n\n"
        f"{'━' * 40}\n\n"
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
    
# Tool: Anteprima risposta
@tool(return_direct=True)
def preview_reply(tool_input, cat):
    """
    Usa questo tool OGNI VOLTA che l'utente vuole rispondere a un'email ricevuta.
    Genera un'anteprima della risposta da mostrare all'utente prima dell'invio.
    Usare SEMPRE prima di send_reply: non inviare mai senza aver mostrato l'anteprima.
    L'input DEVE essere un JSON: {"email_id": 1, "body": "Testo della risposta"}
    'email_id' è il numero intero [ID: N] mostrato accanto all'email quando è stata letta.
    Esempio: {"email_id": 2, "body": "Grazie per il messaggio, rispondo che..."}
    """
    data, error = parse_tool_input(tool_input)
    if data is None: return error
    
    email_id = data.get("email_id")
    body = data.get("body", "").strip()
    
    if not isinstance(email_id, int) or not body:
        return "Errore: fornisci un 'email_id' intero e un 'body' valido."
        
    last_emails = cat.working_memory.get("last_emails", [])
    if not last_emails or email_id < 1 or email_id > len(last_emails):
        return f"Errore: ID {email_id} non trovato. Leggi prima le email per ricaricare la memoria."
        
    target_email = last_emails[email_id - 1]
    
    subject = target_email['subject']
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
        
    recipient = target_email['sender']
    
    return (
        f"ANTEPRIMA RISPOSTA [Rif. ID: {email_id}]\n"
        f"{'━' * 40}\n"
        f"A       : {recipient}\n"
        f"Oggetto : {subject}\n"
        f"{'━' * 40}\n\n"
        f"{body}\n\n"
        f"{'━' * 40}\n\n"
        f"Conferma l'invio della risposta."
    )

# Tool: Invio risposta
@tool(return_direct=True)
def send_reply(tool_input, cat):
    """
    Invia la risposta confermata a un'email. Usare SOLO dopo 'preview_reply'.
    L'input DEVE essere un JSON: {"email_id": 1, "body": "Testo della risposta"}
    """
    data, error = parse_tool_input(tool_input)
    if data is None: return error
    
    email_id = data.get("email_id")
    body = data.get("body", "").strip()
    
    last_emails = cat.working_memory.get("last_emails", [])
    if not last_emails or email_id < 1 or email_id > len(last_emails):
        return f"Errore: ID {email_id} non valido."
        
    target_email = last_emails[email_id - 1]
    subject = target_email['subject']
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
        
    # Estrae solo l'indirizzo email pulito per l'SMTP
    recipient_name, recipient_email = email.utils.parseaddr(target_email['sender'])
    if not recipient_email:
        recipient_email = target_email['sender']
        
    settings = get_settings(cat)
    if not settings.sender_email or not settings.sender_password:
        return "Errore: credenziali SMTP non impostate."

    msg = MIMEMultipart()
    msg['From'] = settings.sender_email
    msg['To'] = target_email['sender']
    msg['Subject'] = subject
    
    # Headers per mantenere la conversazione nei client di posta
    msg_id = target_email.get('message_id')
    if msg_id:
        msg['In-Reply-To'] = msg_id
        msg['References'] = msg_id
        
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    send_ws_notification(cat, f"Invio risposta in corso...", "info")
    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.sender_email, settings.sender_password)
            server.sendmail(settings.sender_email, recipient_email, msg.as_string())
            
        success_msg = f"✓ Risposta inviata con successo a {recipient_email}"
        send_ws_notification(cat, success_msg, "success")
        return success_msg
    except Exception as e:
        err = f"Errore SMTP: {e}"
        send_ws_notification(cat, err, "error")
        return err