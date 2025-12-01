try:
    # LangChain >=0.2 refactor: prefer langchain_core
    from langchain_core.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore
except ImportError:
    # Fallback for older layout
    from langchain.prompts import PromptTemplate, ChatPromptTemplate  # type: ignore

spam_classifier_prompt = PromptTemplate(
    input_variables=["subject", "body"],
    template=(
        "Classify the following email strictly as SPAM or HAM (not spam).\n" 
        "Return JSON with keys: is_spam (true/false), confidence (0-1).\n" 
        "Subject: {subject}\nBody: {body}\n"
        "Always respond in Italian regardless the language of the email."
    ),
)

semantic_analysis_prompt = ChatPromptTemplate.from_messages([
    ("system", "You analyze intent, tone, urgency. Respond in JSON. Always respond in Italian regardless the language of the email."),
    ("human", "Email subject: {subject}\nBody: {body}\nProvide fields: intent, tone, urgency, summary. Always respond in Italian regardless the language of the email."),
    
])

routing_prompt = PromptTemplate(
    input_variables=["intent", "tone", "urgency", "subject", "body"],
    template=(
        "Decide best department for this email among: HR, IT, SALES, FINANCE, SUPPORT.\n"
        "Return JSON with keys: department, rationale.\n"
        "Intent: {intent} | Tone: {tone} | Urgency: {urgency}\n"
        "Subject: {subject}\nBody: {body}\n"
        "Always respond in Italian regardless the language of the email."
    ),
)
