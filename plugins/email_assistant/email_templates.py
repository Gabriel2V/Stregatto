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

# Logica Condivisa 

def _perform_save_template(cat, data: dict) -> str:
    """Logica pura di salvataggio template, usata sia dal Tool che dal Form."""
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
            f"Elimina un template esistente prima di aggiungerne uno nuovo."
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
        f"Oggetto: {subject}\n"
        f"Corpo: {body[:250]}..."
    )

# Tools

@tool(return_direct=True)
def save_email_template(tool_input, cat):
    """
    Salva un template. Input JSON: {"name": "...", "subject": "...", "body": "..."}
    """
    try:
        data = json.loads(tool_input)
    except json.JSONDecodeError as e:
        return f"Errore JSON: {e}"
    
    # Chiama la logica condivisa
    return _perform_save_template(cat, data)

@tool(return_direct=True)
def use_email_template(tool_input, cat):
    """
    Carica un template salvato. Input JSON: {"name": "...", "recipient": "...", "placeholders": {...}}
    """
    try:
        data = json.loads(tool_input)
    except json.JSONDecodeError as e:
        return f"Errore JSON: {e}"

    name = data.get("name", "").strip()
    recipient = data.get("recipient", "").strip()
    placeholders = data.get("placeholders", {})

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

    # Output formattato per guidare l'invio successivo
    return (
        f"Template '{safe_name}' caricato.\n"
        f"Dati pronti:\n"
        f"  Destinatario: {recipient}\n"
        f"  Oggetto: {subject}\n"
        f"  Corpo: {body[:200]}...\n\n"
        f"Usa 'preview_email' per visualizzare l'anteprima finale."
    )

@tool(return_direct=True)
def list_email_templates(tool_input, cat):
    """Mostra tutti i template salvati."""
    templates = load_templates(cat)
    if not templates:
        return "Nessun template salvato."

    lines = [f"Template salvati ({len(templates)}/{MAX_TEMPLATES}):\n"]
    for i, (key, tmpl) in enumerate(templates.items(), 1):
        lines.append(f"{i}. [{key}] - {tmpl.get('subject')}")
    return "\n".join(lines)

@tool(return_direct=True)
def delete_email_template(name, cat):
    """Elimina un template per nome."""
    safe_name = sanitize_name(name)
    templates = load_templates(cat)
    if safe_name in templates:
        del templates[safe_name]
        save_templates(cat, templates)
        return f"Template '{safe_name}' eliminato."
    return "Template non trovato."