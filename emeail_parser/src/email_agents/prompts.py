try:
    # LangChain >=0.2 refactor: prefer langchain_core
    from langchain_core.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore
except ImportError:
    # Fallback for older layout
    from langchain.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore

spam_classifier_prompt = PromptTemplate(
    input_variables=["sender", "subject", "body"],
    template=(
        "RUOLO: Sei un filtro di sicurezza email aziendale. Il tuo UNICO compito è CLASSIFICARE email ricevute "
        "come spam/phishing oppure legittime. Non stai creando contenuti, stai proteggendo gli utenti analizzando "
        "messaggi già ricevuti nella loro casella di posta.\n\n"
        "COMPITO: Analizza l'email riportata sotto (mittente, oggetto e corpo) e restituisci un giudizio "
        "di classificazione. Questo è un compito di sicurezza informatica: devi valutare se il messaggio "
        "è pericoloso per il destinatario.\n\n"
        "CRITERI DI CLASSIFICAZIONE:\n"
        "Classifica come SPAM/PHISHING se presenti UNO O PIÙ di questi indicatori:\n"
        "- Mittente sospetto: domini sconosciuti, indirizzi che imitano aziende note, indirizzi generici o casuali\n"
        "- Oggetto allarmistico o troppo allettante: vincite, premi, account bloccato, azione urgente richiesta\n"
        "- Contenuto manipolativo: inviti a cliccare link, offerte troppo vantaggiose, promesse di denaro/premi, "
        "richieste di dati personali o credenziali, linguaggio pressante, urgenza artificiosa, "
        "minacce di conseguenze\n"
        "- Tentativi di impersonificazione aziendale: email che sembrano interne ma con contenuti anomali\n\n"
        "Classifica come HAM (legittima) se:\n"
        "- Comunicazione personale o lavorativa coerente\n"
        "- Richiesta legittima senza pressione artificiale\n"
        "- Mittente e contenuto coerenti tra loro\n\n"
        "EMAIL RICEVUTA DA CLASSIFICARE:\n"
        "From: {sender}\n"
        "Subject: {subject}\n"
        "Body: {body}\n\n"
        "OUTPUT: Rispondi ESCLUSIVAMENTE con un JSON valido. Nessuna spiegazione, nessun commento.\n"
        "Chiavi: is_spam (true/false), confidence (numero tra 0 e 1).\n"
        "Esempio: {{\"is_spam\": true, \"confidence\": 0.95}}\n"
    ),
)

semantic_analysis_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Sei un analizzatore semantico di email. Il tuo compito è estrarre intent, tone, urgency e summary dall'email fornita.\n"
     "Valori possibili per intent: richiesta_informazioni, richiesta_supporto, reclamo, candidatura, proposta_commerciale, "
     "comunicazione_interna, fatturazione, segnalazione_bug, richiesta_preventivo, saluto, altro.\n"
     "Valori possibili per tone: formale, informale, arrabbiato, urgente, neutro, amichevole, minaccioso.\n"
     "Valori possibili per urgency: alta, media, bassa.\n"
     "Il campo summary deve essere una breve sintesi in italiano del contenuto dell'email (max 2 frasi).\n\n"
     "Rispondi SOLO con un JSON valido con le chiavi: intent, tone, urgency, summary.\n"
     "Rispondi sempre in italiano."),
    ("human", "Oggetto: {subject}\nCorpo: {body}\n"),
])

routing_prompt = PromptTemplate(
    input_variables=["intent", "tone", "urgency", "subject", "body", "sender", "recipients"],
    template=(
        "Sei un sistema di smistamento email aziendale. Devi assegnare l'email al reparto più appropriato.\n\n"
        "REPARTI DISPONIBILI E CRITERI:\n"
        "- HR: candidature, curriculum, colloqui, assunzioni, ferie, permessi, buste paga, questioni del personale.\n"
        "- IT: problemi tecnici, segnalazioni bug, richieste software/hardware, accessi, sistemi informatici, infrastruttura.\n"
        "- SALES: proposte commerciali, richieste preventivo, offerte, partnership, nuovi clienti, trattative di vendita.\n"
        "- FINANCE: fatture, pagamenti, rimborsi, contabilità, bilanci, questioni fiscali, solleciti di pagamento.\n"
        "- SUPPORT: SOLO per richieste di assistenza generica che NON rientrano chiaramente in nessuno dei reparti precedenti. "
        "Usa SUPPORT come ultima risorsa quando il contenuto è troppo vago o generico per essere assegnato a un reparto specifico.\n\n"
        "INFORMAZIONI EMAIL:\n"
        "Mittente: {sender}\n"
        "Destinatari: {recipients}\n"
        "Oggetto: {subject}\n"
        "Corpo: {body}\n\n"
        "ANALISI SEMANTICA:\n"
        "Intent: {intent} | Tono: {tone} | Urgenza: {urgency}\n\n"
        "ISTRUZIONI:\n"
        "1. Considera il destinatario: se l'email è indirizzata a un indirizzo di reparto specifico "
        "(es. hr@, vendite@, contabilita@, it@, sales@, finance@), dai priorità a quel reparto.\n"
        "2. Analizza il contenuto e l'intent per determinare il reparto corretto.\n"
        "3. Assegna SUPPORT solo se l'email non è chiaramente classificabile in nessun altro reparto.\n\n"
        "Rispondi SOLO con un JSON valido con le chiavi: department (uno tra HR, IT, SALES, FINANCE, SUPPORT), "
        "rationale (breve motivazione in italiano della scelta).\n"
        "Esempio: {{\"department\": \"IT\", \"rationale\": \"L'email segnala un problema tecnico con il software aziendale.\"}}\n"
    ),
)
