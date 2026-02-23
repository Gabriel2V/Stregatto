# 📧 Email Assistant — Plugin per Cheshire Cat AI

Un agente AI per la composizione, ottimizzazione e gestione di email aziendali, integrato direttamente nella chat di [Cheshire Cat AI](https://cheshirecat.ai/).

---

## Funzionalità

- **Invio email via SMTP** con anteprima obbligatoria prima della conferma
- **Lettura email via IMAP** con tracciamento delle email già viste
- **Generazione automatica dell'oggetto** tramite LLM, se non fornito dall'utente
- **Ottimizzazione del testo** per rendere le bozze più professionali e formali
- **Template riutilizzabili** con supporto a segnaposto dinamici `{{nome}}`
- **Filtro email per mittente** con ricerca IMAP nativa
- **Configurazione dal pannello Admin del plugin** senza toccare variabili d'ambiente
- **Notifiche WebSocket in tempo reale** sullo stato di ogni operazione

---

## Struttura del plugin

```
email_assistant/
├── main.py               # Settings, hook personalità, tool miglioramento testo
├── email_agent.py        # Tool preview_email e send_email (SMTP)
├── email_reader.py       # Tool check_new_emails e filter_emails_by_sender (IMAP)
├── email_templates.py    # Tool per salvare, usare, elencare ed eliminare template
└── plugin.json           # Metadati del plugin
```

---

## Installazione

1. Clonare le repository
2. Requisiti docker
3. Utilizzare il comando: "docker compose up"
4. Nell'interfaccia Admin di Cheshire Cat, vai su **Plugins**, verifica che il toggle del plugin sia su **On**

## Installazione plugin alternativa (avendo già istanziato Cheshire Cat)

1. Crea una cartella chiamata `email_assistant/`
2. Copia al suo interno tutti i file del plugin
3. Comprimi la cartella in `email_assistant.zip`
4. Nell'interfaccia Admin di Cheshire Cat, vai su **Plugins → Upload plugin** e carica lo zip
5. Verifica che il toggle del plugin sia su **On**

---

## Configurazione

Dopo l'installazione, clicca sulla **rotellina ⚙️** accanto al plugin nell'Admin per aprire il pannello impostazioni e compila i campi:

| Campo | Default | Descrizione |
|---|---|---|
| Email mittente | — | Indirizzo email usato per inviare i messaggi |
| Password / App Password | — | Password dell'account (vedi nota Gmail sotto) |
| Server SMTP | `smtp.gmail.com` | Host del server SMTP |
| Porta SMTP | `587` | Porta SMTP (587 per TLS, 465 per SSL) |
| Server IMAP | `imap.gmail.com` | Host del server IMAP |
| Porta IMAP | `993` | Porta IMAP (SSL) |
| Email da recuperare | `5` | Numero massimo di email per controllo (1–20) |
| Lunghezza anteprima corpo | `500` | Caratteri mostrati nell'anteprima (100–2000) |

### ⚠️ Nota per Gmail

Google non consente l'accesso diretto con la password dell'account. È necessaria un'**App Password**:

1. Vai su [myaccount.google.com](https://myaccount.google.com) → **Sicurezza**
2. Attiva la **Verifica in due passaggi**
3. Cerca **"Password per le app"** e genera una nuova password per "Mail"
4. Usa la stringa di 16 caratteri generata come password nel plugin

Lo stesso processo si applica a **Outlook/Hotmail** e altri provider moderni.

---

## Utilizzo

Interagisci con il plugin direttamente nella chat. L'agente riconosce automaticamente l'intento e invoca il tool corretto.

### Inviare un'email

```
Invia un'email a mario.rossi@azienda.it per comunicargli che 
la riunione di domani è spostata alle 15:00.
```

Il flusso prevede:
1. Il tool `preview_email` mostra un'anteprima con oggetto (generato automaticamente se non fornito)
2. L'utente conferma
3. Il tool `send_email` esegue l'invio tramite SMTP

### Migliorare un testo

```
Migliora questo testo: "ciao, ti scrivo per dirti che non riesco 
a venire alla riunione, scusa"
```

### Controllare le nuove email

```
Ci sono nuove email?
```

### Filtrare email per mittente

```
Mostrami tutte le email di fornitore@esempio.it
```

### Gestire i template

**Salvare un template:**
```
Salva un template chiamato "follow_up" con oggetto 
"Follow-up riunione del {{data}}" e corpo 
"Gentile {{nome}}, in seguito alla riunione di ieri..."
```

**Usare un template:**
```
Usa il template "follow_up" per inviare un'email a 
luca.bianchi@azienda.it, con nome "Luca" e data "20 febbraio"
```

**Elencare i template salvati:**
```
Mostrami tutti i template che ho salvato
```

**Eliminare un template:**
```
Elimina il template "follow_up"
```

---

## Tool disponibili

| Tool | File | Descrizione |
|---|---|---|
| `improve_email_text` | `main.py` | Riscrive un testo in chiave professionale |
| `preview_email` | `email_agent.py` | Genera anteprima prima dell'invio |
| `send_email` | `email_agent.py` | Invia l'email via SMTP |
| `check_new_emails` | `email_reader.py` | Recupera le nuove email dalla inbox |
| `filter_emails_by_sender` | `email_reader.py` | Cerca email per mittente |
| `save_email_template` | `email_templates.py` | Salva un template riutilizzabile |
| `use_email_template` | `email_templates.py` | Carica un template per l'invio |
| `list_email_templates` | `email_templates.py` | Elenca tutti i template salvati |
| `delete_email_template` | `email_templates.py` | Elimina un template |

---

## Requisiti

- Docker/Docker Desktop installato e avviato
- [Cheshire Cat AI](https://github.com/cheshire-cat-ai/core) installato e avviato
- Account email con accesso SMTP/IMAP abilitato
- Python 3.10+ (incluso nell'ambiente Cheshire Cat)
- Nessuna dipendenza esterna: usa solo librerie della standard library Python (`imaplib`, `smtplib`, `email`)

---

## Autore

**Gabriele Vizzi**