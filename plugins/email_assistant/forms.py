from pydantic import BaseModel, Field
from cat.experimental.form import CatForm, form
from .main import generate_email_subject
from .email_sender import validate_email_input
from .email_templates import _perform_save_template

# Modelli dati 

class EmailDraft(BaseModel):
    recipient: str = Field(
        description="A quale indirizzo email vuoi inviare il messaggio?"
    )
    subject: str = Field(
        default="",
        description="Qual è l'oggetto dell'email? (Scrivi 'auto' o lascia vuoto per generarlo automaticamente)"
    )
    body: str = Field(
        description="Dettami il testo del corpo dell'email."
    )

class TemplateDraft(BaseModel):
    name: str = Field(
        description="Che nome vuoi dare a questo template? (es. 'invio_fattura')"
    )
    subject: str = Field(
        description="Qual è l'oggetto di default per questo template? (Puoi usare {{nome}} come segnaposto)"
    )
    body: str = Field(
        description="Qual è il testo del template? (Puoi usare {{nome}} come segnaposto)"
    )

# Forms

@form
class EmailCompositionForm(CatForm):
    description = "Form per comporre e preparare una nuova email passo dopo passo"
    model_class = EmailDraft

    start_examples = [
        "voglio scrivere un'email",
        "prepara una nuova email",
        "scrivi una mail",
        "componi un messaggio di posta"
    ]
    stop_examples = [
        "annulla",
        "ferma tutto",
        "non voglio più scrivere l'email",
        "esci",
        "basta così"
    ]

    def submit(self, form_data):
        # Recupero dati
        recipient = form_data.get("recipient")
        body = form_data.get("body")
        subject = form_data.get("subject", "")

        if not subject or subject.lower().strip() in ["auto", "generalo tu", "fai tu"]:
            subject = generate_email_subject(body,self.cat)
            auto_note = " (generato automaticamente dall'AI)"
        else:
            auto_note = ""

        return (
            f"ANTEPRIMA EMAIL (Da Form)\n"
            f"{'━' * 40}\n"
            f"Destinatario : {recipient}\n"
            f"Oggetto      : {subject}{auto_note}\n"
            f"{'━' * 40}\n\n"
            f"{body}\n\n"
            f"{'━' * 40}\n\n"
            f"I dati sono corretti? Se confermi, scrivi 'Invia email' e procederò."
        )

@form
class TemplateCreationForm(CatForm):
    description = "Form per creare e salvare un nuovo template email"
    model_class = TemplateDraft

    start_examples = [
        "voglio creare un template",
        "salva un nuovo template",
        "crea modello email",
        "registra un template"
    ]
    stop_examples = [
        "annulla",
        "ferma tutto",
        "esci",
        "annulla template"
    ]

    def submit(self, form_data):
        result_message = _perform_save_template(self.cat, form_data)
        
        return result_message