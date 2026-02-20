import stmlib
import json
import re
from email.mine.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cat.mad_hatter.decorators import tool, hook

#hooks per il contesto

@hook 
def agent_prompt_prefix(prefix, cat):
    """
    Questo hook inietta istruzioni di sistema nel prompt iniziale del Cat.
    Definisce il suo ruolo, gli ordina di suggerire miglioramenti e
    gli spiega come gestire la mancanza dell'oggetto della mail.
    """
    email_context = """
    Sei un assistente virtuale altamente qualificato nella gestione delle e-mail.
    I tuoi compiti principali sono:
    1. Aiutare l'utente a redigere e-mail chiare, professionali e prive di errori. Se il testo dell'utente è migliorabile, proponi sempre una versione rivista usando il tool 'improve_email_text'.
    2. Raccogliere i dati per l'invio: destinatario, oggetto e corpo della mail.
    3. SE L'UTENTE NON FORNISCE L'OGGETTO, DEVI GENERARLO TU automaticamente basandoti sul contenuto del corpo del messaggio prima di inviare l'e-mail.
    4. Quando hai tutti i dati, usa il tool 'send_email' per inviare il messaggio.
    """
    return f"{prefix}\n{email_context}"
