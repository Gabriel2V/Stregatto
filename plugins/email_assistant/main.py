from pydantic import BaseModel, Field
from cat.mad_hatter.decorators import tool, hook, plugin
from cat.mad_hatter.mad_hatter import MadHatter


#  Settings del plugin di cheshire cat ai
#  esposti nel pannello Admin → Plugin → Email Assistant

class EmailAssistantSettings(BaseModel):
    """Configurazione del plugin Email Assistant."""

    # Credenziali mittente
    sender_email: str = Field(
        default="",
        title="Email mittente",
        description="Indirizzo email usato per inviare i messaggi."
    )
    sender_password: str = Field(
        default="",
        title="Password / App Password",
        description="Password dell'account o App Password (consigliata per Gmail)."
    )

    # SMTP
    smtp_server: str = Field(
        default="smtp.gmail.com",
        title="Server SMTP",
        description="Host del server SMTP."
    )
    smtp_port: int = Field(
        default=587,
        title="Porta SMTP",
        description="Porta SMTP (587 per TLS, 465 per SSL)."
    )

    # IMAP
    imap_server: str = Field(
        default="imap.gmail.com",
        title="Server IMAP",
        description="Host del server IMAP."
    )
    imap_port: int = Field(
        default=993,
        title="Porta IMAP",
        description="Porta IMAP (di solito 993 per SSL)."
    )

    # Comportamento
    max_emails_to_fetch: int = Field(
        default=5,
        title="Email da recuperare",
        description="Numero massimo di email da analizzare ad ogni controllo (1–20).",
        ge=1,
        le=20
    )
    email_preview_length: int = Field(
        default=500,
        title="Lunghezza anteprima corpo",
        description="Numero massimo di caratteri mostrati nell'anteprima del corpo email.",
        ge=100,
        le=2000
    )
    
@plugin
def settings_model():
    return EmailAssistantSettings

def get_settings(cat) -> EmailAssistantSettings:
    """
    Helper globale: restituisce le impostazioni correnti del plugin.
    Tutti i moduli del plugin usano questa funzione
    """
    raw = cat.mad_hatter.get_plugin().load_settings()
    return EmailAssistantSettings(**raw) if raw else EmailAssistantSettings()


# Funzioni di utility interna 

def send_ws_notification(cat, message: str, notification_type: str = "info") -> None:
    """Invia una notifica WebSocket all'utente per aggiornamenti di stato."""
    try:
        cat.send_ws_message(content=message, msg_type="notification")
    except Exception as e:
        print(f"[EmailAssistant] Errore invio WebSocket ({notification_type}): {e}")


def generate_email_subject(body: str, cat) -> str:
    """
    Genera un oggetto professionale e conciso analizzando il corpo del messaggio.
    Restituisce una stringa pulita, senza virgolette o testo superfluo.
    """
    send_ws_notification(cat, "Analisi del testo e generazione oggetto in corso...", "info")
    prompt = f"""
Crea un oggetto altamente professionale, conciso e persuasivo (massimo 8-10 parole) 
per la seguente email aziendale.
L'oggetto deve riassumere il punto chiave del messaggio.
Rispondi ESCLUSIVAMENTE con l'oggetto, senza alcun testo aggiuntivo, 
virgolette, prefissi o punteggiatura superflua.

Contenuto email:
{body}
"""
    subject = cat.llm(prompt).strip().strip('"').strip("'")
    send_ws_notification(cat, f"Oggetto generato: '{subject}'", "success")
    return subject


#  Hook per personalità aziendale

@hook(priority=0)
def agent_prompt_prefix(prefix, cat):
    """
    Sostituzione totale del prefix di base. 
    Il modello non saprà mai di essere stato lo Stregatto.
    """
    corporate_context = """Sei un assistente AI aziendale impersonale, formale, diretto e strettamente professionale,
specializzato nell'elaborazione e gestione di posta elettronica.

REGOLE DI COMUNICAZIONE:
1. Usa un tono neutro, corporativo e distaccato ma formale.
2. Vai dritto al punto, senza saluti stravaganti o convenevoli inutili.
3. Per migliorare testi usa il tool 'improve_email_text'.
4. Per inviare email usa prima 'preview_email', poi 'send_email' su conferma dell'utente.
5. Per controllare le email appena arrivate usa 'check_new_emails'. Per leggere o riassumere le ultime email in generale usa 'read_latest_emails'.
6. Per gestire i template usa 'save_email_template' e 'use_email_template'.
7. Per filtrare email per mittente usa 'filter_emails_by_sender'."""
    
    # Restituiamo il contesto attuale, scartando del tutto il 'prefix' originale
    return corporate_context


# Tool per miglioramento testo email bozza

@tool
def improve_email_text(testo, cat):
    """
    Rielabora il testo fornito per renderlo più professionale, chiaro ed efficace.
    Input: bozza o appunti dell'utente.
    Output: versione riscritta e ottimizzata per la comunicazione aziendale.
    """
    send_ws_notification(cat, "Ottimizzazione del testo e del tono di voce in corso...", "info")
    prompt = f"""
Riscrivi il seguente testo per un'email aziendale.
Obiettivo: renderlo altamente professionale, cortese, chiaro e privo di errori grammaticali.
Il tono deve essere adeguato a un contesto lavorativo formale e impersonale.
Mantieni inalterate le informazioni chiave e l'intento originale.
Restituisci SOLO il testo riscritto, senza introduzioni o commenti.

Testo originale:
{testo}
"""
    improved_text = cat.llm(prompt)
    send_ws_notification(cat, "Ottimizzazione del testo completata.", "success")
    return improved_text