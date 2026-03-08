try:
    # LangChain >=0.2 refactor: prefer langchain_core
    from langchain_core.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore
except ImportError:
    # Fallback for older layout
    from langchain.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore

spam_classifier_prompt = PromptTemplate(
    input_variables=["subject", "body"],
    template=(
        "Sei un classificatore anti-spam. Analizza l'email seguente e stabilisci se è SPAM o HAM (non spam).\n"
        "Considera come indicatori di spam: link sospetti, offerte troppo vantaggiose, richieste di dati personali, "
        "mittenti sconosciuti con contenuti generici, linguaggio pressante o ingannevole.\n"
        "Considera come HAM: comunicazioni personali, lavorative, richieste legittime, risposte a conversazioni esistenti.\n\n"
        "Subject: {subject}\nBody: {body}\n\n"
        "Rispondi SOLO con un JSON valido con le chiavi: is_spam (true/false), confidence (numero tra 0 e 1).\n"
        "Esempio: {{\"is_spam\": false, \"confidence\": 0.95}}\n"
        "Rispondi sempre in italiano."
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
