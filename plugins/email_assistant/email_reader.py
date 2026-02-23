import imaplib
import email
import json
import os
from email.header import decode_header
from cat.mad_hatter.decorators import tool, hook
from cat.log import log

from .main import send_ws_notification, get_settings

# Variabile globale per salvare la sessione utente attiva
_active_cat = None

@hook
def before_cat_reads_message(user_message_json, cat):
    """
    Cattura l'istanza StrayCat (legata alla sessione utente corrente)
    così lo scheduler in background sa a quale WebSocket inviare le notifiche.
    """
    global _active_cat
    _active_cat = cat
    return user_message_json

# Storage condiviso (file JSON)
# Un file JSON nella cartella del plugin sincronizza il cursore UID tra
# lo scheduler e il tool manuale.
# Il file sopravvive anche ai riavvii del container

_STATE_FILE = os.path.join(os.path.dirname(__file__), ".email_state.json")


def _read_last_uid() -> int:
    """Legge l'ultimo UID controllato dal file di stato."""
    try:
        with open(_STATE_FILE, "r") as f:
            return json.load(f).get("last_email_uid", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def _write_last_uid(uid: int) -> None:
    """Scrive l'ultimo UID controllato nel file di stato."""
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({"last_email_uid": uid}, f)
    except Exception as e:
        log.error(f"[EmailAssistant] Errore scrittura file di stato: {e}")


# Scheduler

CHECK_INTERVAL_MINUTES = 2


def _scheduled_email_check(cat_core):
    """
    Funzione chiamata dal White Rabbit ogni N minuti.
    Usa la variabile globale _active_cat per inviare il messaggio alla chat attiva.
    """
    global _active_cat
    if _active_cat is None:
        return

    settings = get_settings(_active_cat)

    if not settings.sender_email or not settings.sender_password or not settings.imap_server:
        log.warning("[EmailScheduler] Credenziali non configurate, skip.")
        return

    result = _fetch_new_emails_sync(settings)
    if result is None:
        return  # Nessuna novità, silenzio

    new_emails_data, formatted_text = result 
    new_count = len(new_emails_data)
    _active_cat.working_memory.last_emails = new_emails_data 
    
    log.info(f"[EmailScheduler] {new_count} nuove email trovate.")

    message = f" **{new_count} nuov{'a email' if new_count == 1 else 'e email'} ricevut{'a' if new_count == 1 else 'e'}**\n\n{formatted_text}"
    try:
        # Usa l'istanza StrayCat salvata per inviare il messaggio
        _active_cat.send_ws_message(content=message, msg_type="chat")
    except Exception as e:
        log.error(f"[EmailScheduler] Errore invio notifica WebSocket: {e}")


@hook(priority=1)
def after_cat_bootstrap(cat):
    """
    Registra il controllo periodico tramite White Rabbit (scheduler interno del Cat).
    White Rabbit chiama la funzione con la StrayCat della sessione corrente,
    che ha una connessione WebSocket attiva → send_ws_message funziona.
    """
    job_id = "email_scheduler_check"

    # Evita duplicati: rimuove il job precedente se esiste
    existing_job = cat.white_rabbit.scheduler.get_job(job_id)
    if existing_job is not None:
        cat.white_rabbit.remove_job(job_id)

    cat.white_rabbit.schedule_interval_job(
        _scheduled_email_check,
        seconds=CHECK_INTERVAL_MINUTES * 60,
        job_id=job_id,
        cat_core=cat
    )
    log.info(f"[EmailScheduler] Job schedulato ogni {CHECK_INTERVAL_MINUTES} minuti (id: {job_id}).")


# Fetch condiviso
# Legge/scrive il cursore UID sul file JSON

def _fetch_new_emails_sync(settings) -> tuple | None:
    """
    Recupera le nuove email confrontando con l'ultimo UID nel file di stato.
    Restituisce (count, testo_formattato) oppure None se non ci sono novità.
    Usata sia dallo scheduler che dal tool manuale check_new_emails.
    """
    try:
        mail = connect_imap(settings)
        mail.select("inbox")

        status, messages = mail.uid('search', None, "ALL")
        if status != 'OK':
            mail.logout()
            return None

        uids = messages[0].split()
        if not uids:
            mail.logout()
            return None

        last_uid = _read_last_uid()
        new_uids = [uid for uid in uids if int(uid) > last_uid]
        if not new_uids:
            mail.logout()
            return None

        uids_to_process = new_uids[-settings.max_emails_to_fetch:]
        highest_uid = max(int(uid) for uid in uids_to_process)

        emails_data = fetch_email_summaries(mail, uids_to_process, settings.email_preview_length)
        mail.logout()

        if not emails_data:
            return None

        _write_last_uid(highest_uid)
        return emails_data, format_email_list(emails_data)

    except imaplib.IMAP4.error as e:
        log.error(f"[EmailAssistant] Errore autenticazione IMAP: {e}")
        return None
    except Exception as e:
        log.error(f"[EmailAssistant] Errore imprevisto fetch: {e}")
        return None


# Utility IMAP

def get_email_body(msg) -> str:
    """Estrae il corpo testuale dell'email. Gestisce multipart e messaggi semplici."""
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
    """Recupera mittente, oggetto, anteprima e Message-ID per ogni UID fornito."""
    emails_data = []
    for uid in uids_to_process:
        try:
            res, msg_data = mail.uid('fetch', uid, '(BODY.PEEK[])')
            if res != 'OK':
                continue
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = decode_header_value(msg.get("Subject", "(nessun oggetto)"))
                    sender = decode_header_value(msg.get("From", "(mittente sconosciuto)"))
                    message_id = decode_header_value(msg.get("Message-ID", "")) # <--- NUOVO
                    body = get_email_body(msg)
                    emails_data.append({
                        "uid": int(uid),
                        "sender": sender,
                        "subject": subject,
                        "message_id": message_id, # <--- NUOVO
                        "body_preview": body[:preview_length]
                    })
        except Exception as e:
            print(f"[EmailAssistant] Errore elaborazione UID {uid}: {e}")
    return emails_data


def format_email_list(emails_data: list) -> str:
    """Formatta una lista di dizionari email in testo leggibile con ID."""
    parts = []
    for i, e in enumerate(emails_data, 1):
        parts.append(
            f"[ID: {i}] Da: {e['sender']}\n"
            f"Oggetto: {e['subject']}\n"
            f"Messaggio:\n{e['body_preview']}..."
        )
    return "Email trovate:\n\n" + "\n\n---\n\n".join(parts)


# Tool: controllo manuale nuove mail

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

    result = _fetch_new_emails_sync(settings)

    if result is None:
        send_ws_notification(cat, "Nessuna nuova email trovata.", "info")
        return "Nessun nuovo messaggio dall'ultimo controllo."

    new_emails_data, formatted_text = result
    cat.working_memory.last_emails = new_emails_data
    
    send_ws_notification(cat, f"Trovate {len(new_emails_data)} nuove email.", "success")
    return formatted_text


# Tool: filtro per mittente 

@tool
def filter_emails_by_sender(sender_filter, cat):
    """
    Cerca le email nella casella di posta provenienti da uno specifico mittente e mostra le più recenti.
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

        uids_to_process = uids[-settings.max_emails_to_fetch:]
        emails_data = fetch_email_summaries(mail, uids_to_process, settings.email_preview_length)
        mail.logout()

        if not emails_data:
            return f"Email trovate ma impossibile decodificarle da '{sender_filter}'."

        send_ws_notification(cat, f"Trovate {len(emails_data)} email da '{sender_filter}'.", "success")

        parts = []
        for e in emails_data:
            parts.append(
                f"Da: {e['sender']}\n"
                f"Oggetto: {e['subject']}\n"
                f"Messaggio:\n{e['body_preview']}..."
            )
        cat.working_memory.last_emails = emails_data
        return (
            f"Email da '{sender_filter}' ({len(emails_data)} trovate):\n\n"
            + "\n\n---\n\n".join(parts)
        )

    except imaplib.IMAP4.error as e:
        return f"Errore di autenticazione IMAP: {e}"
    except Exception as e:
        print(f"[EmailAssistant] Errore imprevisto filter_emails_by_sender: {e}")
        return f"Errore durante il filtro per mittente: {e}"
    
# Tool: lettura ultime mail (ignora lo stato di lettura)

@tool
def read_latest_emails(tool_input, cat):
    """
    Legge e recupera le ultime email ricevute, indipendentemente dal fatto che siano già state lette.
    Usa SEMPRE questo tool quando l'utente chiede di "leggere", "riassumere" o "mostrare" le ultime email.
    Non richiede alcun input specifico.
    """
    send_ws_notification(cat, "Recupero delle ultime email in corso...", "info")

    settings = get_settings(cat)
    if not settings.sender_email or not settings.sender_password:
        return "Errore: credenziali IMAP non configurate. Vai in Admin → Plugin → Email Assistant."

    try:
        mail = connect_imap(settings)
        mail.select("inbox")

        status, messages = mail.uid('search', None, "ALL")
        if status != 'OK':
            mail.logout()
            return "Errore durante il recupero delle email dalla casella di posta."

        uids = messages[0].split()
        if not uids:
            mail.logout()
            send_ws_notification(cat, "La casella di posta è vuota.", "info")
            return "Nessun messaggio presente nella casella di posta."

        # Prende gli ultimi N messaggi in base alle impostazioni, ignorando il file di stato
        uids_to_process = uids[-settings.max_emails_to_fetch:]
        
        emails_data = fetch_email_summaries(mail, uids_to_process, settings.email_preview_length)
        mail.logout()

        if not emails_data:
            return "Impossibile recuperare o decodificare le ultime email."

        send_ws_notification(cat, f"Recuperate le ultime {len(emails_data)} email.", "success")
        
        cat.working_memory.last_emails = emails_data
        # Rimuove l'intestazione standard di format_email_list per adattarla al contesto
        formatted_list = format_email_list(emails_data).replace("Nuove email trovate:\n\n", "")
        return f"Ultime {len(emails_data)} email presenti in casella:\n\n{formatted_list}"

    except imaplib.IMAP4.error as e:
        return f"Errore di autenticazione IMAP: {e}"
    except Exception as e:
        log.error(f"[EmailAssistant] Errore imprevisto in read_latest_emails: {e}")
        return f"Errore durante la lettura delle email: {e}"