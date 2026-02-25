import json
from cat.mad_hatter.decorators import tool

from .main import send_ws_notification

# Chiavi di memoria
TEMPLATES_MEMORY_KEY = "email_templates"
MAX_TEMPLATES = 20

# Funzioni di utility interna

def load_templates(cat) -> dict:
    """Carica il dizionario dei template dalla memoria episodica del Cat."""
    raw = getattr(cat.working_memory, "email_templates", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[EmailAssistant] Errore caricamento template: {e}")
        return {}


def save_templates(cat, templates: dict) -> None:
    """Salva il dizionario dei template nella memoria episodica del Cat."""
    cat.working_memory.email_templates = templates


def sanitize_name(name: str) -> str:
    """Normalizza il nome del template: minuscolo, spazi → underscore."""
    return name.strip().lower().replace(" ", "_")

#  Tool salva template

@tool(return_direct=True)
def save_email_template(tool_input, cat):
    """
    Salva un template di email riutilizzabile con un nome identificativo.
    Utile per email ricorrenti (es. follow-up, presentazioni, richieste standard).
    L'input DEVE essere un JSON valido con questa struttura:
    {"name": "nome_template", "subject": "Oggetto email", "body": "Corpo del messaggio"}
    Il nome deve essere univoco: se esiste già un template con lo stesso nome, verrà sovrascritto.
    Esempio: {"name": "follow_up", "subject": "Follow-up riunione", "body": "Gentile..."}
    """
    try:
        data = json.loads(tool_input)
    except json.JSONDecodeError as e:
        return f"Errore: il formato JSON fornito non è valido. Dettaglio: {e}"

    name = data.get("name", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()

    if not name:
        return "Errore: il campo 'name' è obbligatorio per salvare un template."
    if not body or len(body) < 10:
        return "Errore: il corpo del template è troppo breve (minimo 10 caratteri)."

    safe_name = sanitize_name(name)
    templates = load_templates(cat)

    if len(templates) >= MAX_TEMPLATES and safe_name not in templates:
        return (
            f"Errore: limite di {MAX_TEMPLATES} template raggiunto. "
            f"Elimina un template esistente con 'delete_email_template' prima di aggiungerne uno nuovo."
        )

    is_update = safe_name in templates
    templates[safe_name] = {
        "name": safe_name,
        "subject": subject,
        "body": body
    }
    save_templates(cat, templates)

    action = "aggiornato" if is_update else "salvato"
    send_ws_notification(cat, f"Template '{safe_name}' {action}.", "success")
    return (
        f"Template '{safe_name}' {action} con successo.\n"
        f"Oggetto: {subject if subject else '(nessuno – verrà generato automaticamente)'}\n"
        f"Corpo: {body[:100]}{'...' if len(body) > 100 else ''}"
    )


#  Tool per usare template

@tool(return_direct=True)
def use_email_template(tool_input, cat):
    """
    Carica un template salvato e prepara i dati per l'invio, sostituendo eventuali segnaposto.
    L'input DEVE essere un JSON valido con questa struttura:
    {"name": "nome_template", "recipient": "email@esempio.com", "placeholders": {"nome": "Mario", "azienda": "Acme"}}
    Il campo 'placeholders' è opzionale: se fornito, sostituisce i segnaposto {{chiave}} nel template.
    Esempio segnaposto nel template: "Gentile {{nome}}, come sta {{azienda}}?"
    Dopo il caricamento, usa 'preview_email' per visualizzare l'anteprima e poi 'send_email' per inviare.
    """
    try:
        data = json.loads(tool_input)
    except json.JSONDecodeError as e:
        return f"Errore: il formato JSON fornito non è valido. Dettaglio: {e}"

    name = data.get("name", "").strip()
    recipient = data.get("recipient", "").strip()
    placeholders = data.get("placeholders", {})

    if not name:
        return "Errore: il campo 'name' è obbligatorio."
    if not recipient:
        return "Errore: il campo 'recipient' è obbligatorio."

    safe_name = sanitize_name(name)
    templates = load_templates(cat)

    if safe_name not in templates:
        available = ", ".join(templates.keys()) if templates else "nessuno"
        return (
            f"Errore: template '{safe_name}' non trovato.\n"
            f"Template disponibili: {available}"
        )

    template = templates[safe_name]
    subject = template.get("subject", "")
    body = template.get("body", "")

    # Sostituzione segnaposto {{chiave}} → valore
    if placeholders and isinstance(placeholders, dict):
        for key, value in placeholders.items():
            placeholder_tag = f"{{{{{key}}}}}"
            subject = subject.replace(placeholder_tag, str(value))
            body = body.replace(placeholder_tag, str(value))

    send_ws_notification(cat, f"Template '{safe_name}' caricato.", "info")

    return (
        f"Template '{safe_name}' caricato con successo.\n"
        f"Dati pronti per l'invio:\n"
        f"  Destinatario: {recipient}\n"
        f"  Oggetto: {subject if subject else '(verrà generato automaticamente)'}\n"
        f"  Corpo: {body[:200]}{'...' if len(body) > 200 else ''}\n\n"
        f"Usa 'preview_email' con il JSON seguente per visualizzare l'anteprima:\n"
        f'{json.dumps({"recipient": recipient, "subject": subject, "body": body}, ensure_ascii=False)}'
    )


# Tool per lista template

@tool(return_direct=True)
def list_email_templates(tool_input, cat):
    """
    Mostra tutti i template email salvati con nome, oggetto e anteprima del corpo.
    Non richiede alcun input specifico.
    """
    templates = load_templates(cat)

    if not templates:
        return "Nessun template salvato. Usa 'save_email_template' per crearne uno."

    lines = [f"Template salvati ({len(templates)}/{MAX_TEMPLATES}):\n"]
    for i, (key, tmpl) in enumerate(templates.items(), 1):
        subject_display = tmpl.get("subject") or "(oggetto auto-generato)"
        body_preview = tmpl.get("body", "")[:80]
        lines.append(
            f"{i}. [{key}]\n"
            f"   Oggetto: {subject_display}\n"
            f"   Corpo  : {body_preview}{'...' if len(tmpl.get('body', '')) > 80 else ''}"
        )

    return "\n".join(lines)


#  Tool per eliminare template

@tool(return_direct=True)
def delete_email_template(name, cat):
    """
    Elimina un template email salvato identificato dal suo nome.
    Input: nome del template da eliminare (es. 'follow_up').
    """
    if not name or len(name.strip()) < 1:
        return "Errore: fornisci il nome del template da eliminare."

    safe_name = sanitize_name(name)
    templates = load_templates(cat)

    if safe_name not in templates:
        available = ", ".join(templates.keys()) if templates else "nessuno"
        return (
            f"Errore: template '{safe_name}' non trovato.\n"
            f"Template disponibili: {available}"
        )

    del templates[safe_name]
    save_templates(cat, templates)

    send_ws_notification(cat, f"Template '{safe_name}' eliminato.", "success")
    return f"Template '{safe_name}' eliminato con successo."