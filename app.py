import asyncio
import time

import edge_tts
import language_tool_python
import streamlit as st

# ---------------- Configuración ----------------
st.set_page_config(page_title="🇬🇧 Learn British English", page_icon="🎓",
                   layout="wide")

st.markdown(
    """
    <style>
      .hero {
        background: linear-gradient(120deg, #012169 0%, #C8102E 100%);
        padding: 1.6rem 2rem; border-radius: 1rem; color: white;
        margin-bottom: 1.2rem;
      }
      .hero h1 { margin: 0; font-size: 1.8rem; }
      .hero p  { margin: 0.3rem 0 0; opacity: 0.9; }
      .card {
        background: rgba(128,128,128,0.06);
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 0.9rem; padding: 1.2rem 1.4rem; margin-bottom: 1rem;
      }
      .credit { text-align: center; padding: 1rem 0 0.2rem; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>🇬🇧 Learn British English</h1>
      <p>De cero (A1) hasta C2 — lee, escucha, escribe y recibe correcciones.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Voces británicas ----------------
VOICES = {
    "🇬🇧 Voz masculina (Ryan)": "en-GB-RyanNeural",
    "🇬🇧 Voz femenina (Sonia)": "en-GB-SoniaNeural",
    "🇬🇧 Voz masculina (Thomas)": "en-GB-ThomasNeural",
    "🇬🇧 Voz femenina (Libby)": "en-GB-LibbyNeural",
}

# ---------------- Contenido: lecciones por nivel ----------------
LECCIONES = {
    "A1 – Principiante": [
        {
            "titulo": "My Family",
            "parrafo": ("My name is Tom. I live in a small flat in London with my "
                        "family. My mother is a nurse and my father is a bus driver. "
                        "I have one sister. Her name is Emma. She is seven years old. "
                        "We have a cat called Whiskers. Every morning, I eat toast "
                        "and drink tea for breakfast."),
        },
        {
            "titulo": "A Day at School",
            "parrafo": ("I go to school by bus. My school is near the park. "
                        "Lessons start at nine o'clock. My favourite subject is "
                        "history. At lunchtime, I eat sandwiches with my friends. "
                        "After school, I play football in the garden."),
        },
    ],
    "A2 – Elemental": [
        {
            "titulo": "A Weekend in the Countryside",
            "parrafo": ("Last weekend, we visited my grandmother in the countryside. "
                        "The weather was lovely, so we went for a long walk across "
                        "the fields. We saw sheep and cows everywhere. My grandmother "
                        "cooked a traditional Sunday roast with vegetables from her "
                        "garden. It was delicious."),
        },
        {
            "titulo": "My Favourite Hobby",
            "parrafo": ("I really enjoy reading books about British history. I "
                        "usually read in the evenings, after finishing my homework. "
                        "At the moment, I am reading a novel about the Victorians. "
                        "Reading helps me learn new vocabulary and improves my "
                        "writing too."),
        },
    ],
    "B1 – Intermedio": [
        {
            "titulo": "Working in a Café",
            "parrafo": ("I have been working in a busy café in Manchester since "
                        "January. Although it can be tiring, I love meeting "
                        "customers from all over the world. My colleagues are "
                        "friendly, and we often help each other during the busiest "
                        "hours. In the future, I would like to open my own little "
                        "tea shop by the seaside."),
        },
        {
            "titulo": "The Weather in Britain",
            "parrafo": ("British people are famous for talking about the weather, "
                        "and there is a good reason for it: it changes constantly. "
                        "One moment the sky is grey and it is drizzling, and the "
                        "next the sun is shining. Because of this, most people "
                        "carry an umbrella wherever they go, just in case."),
        },
    ],
    "B2 – Intermedio alto": [
        {
            "titulo": "The Importance of Public Libraries",
            "parrafo": ("Public libraries have played a remarkable role in British "
                        "society for centuries. Not only do they provide free access "
                        "to books and the internet, but they also serve as community "
                        "hubs where people of all ages can learn new skills. Despite "
                        "budget cuts in recent years, many libraries have adapted by "
                        "offering workshops, coding clubs, and reading groups, which "
                        "proves how valuable they remain to local communities."),
        },
        {
            "titulo": "Sustainable Travel",
            "parrafo": ("More and more travellers are choosing sustainable options "
                        "when planning their holidays. Rather than flying, some "
                        "people now take the train across Europe, enjoying the "
                        "scenery while reducing their carbon footprint. However, "
                        "critics argue that slow travel is a luxury that not everyone "
                        "can afford, which raises important questions about fairness "
                        "in the movement towards greener tourism."),
        },
    ],
    "C1 – Avanzado": [
        {
            "titulo": "The Evolution of the English Language",
            "parrafo": ("The English language has undergone profound transformations "
                        "throughout its history, absorbing vocabulary from Latin, "
                        "French, and Norse, among countless other sources. What "
                        "distinguishes British English from its American counterpart "
                        "is not merely spelling or pronunciation, but subtle "
                        "differences in idiom and register. Linguists contend that "
                        "these variations, far from being deficiencies, enrich the "
                        "language and reflect the cultural identity of their "
                        "speakers."),
        },
        {
            "titulo": " remote Work and Society",
            "parrafo": ("The widespread adoption of remote work has reshaped urban "
                        "life in ways few could have anticipated. City centres, once "
                        "bustling with commuters, have had to reinvent themselves to "
                        "attract visitors, while rural areas have experienced an "
                        "unprecedented influx of professionals seeking a better "
                        "quality of life. Whether this shift will endure remains to "
                        "be seen, yet its implications for housing, transport, and "
                        "social cohesion are already unmistakable."),
        },
    ],
    "C2 – Maestría": [
        {
            "titulo": "On the Subtlety of Irony",
            "parrafo": ("Irony, that most British of rhetorical devices, thrives on "
                        "the tension between what is said and what is meant. Its "
                        "deployment requires not only linguistic dexterity but also a "
                        "sophisticated awareness of context and audience, for irony "
                        "poorly executed is indistinguishable from sincerity. "
                        "Scholars have long debated whether irony constitutes a "
                        "defence mechanism against earnestness or, conversely, a "
                        "vehicle through which uncomfortable truths may be uttered "
                        "with plausible deniability."),
        },
    ],
}

# ---------------- Utilidades ----------------
@st.cache_resource
def obtener_correccion():
    """LanguageTool en inglés británico (sin API key)."""
    return language_tool_python.LanguageTool("en-GB")


async def generar_fragmento(texto: str, voz: str, rate: str) -> bytes:
    for intento in range(3):
        buffer = bytearray()
        try:
            comun = edge_tts.Communicate(texto.strip(), voz, rate=rate)
            async for mensaje in comun.stream():
                if mensaje.get("type") == "audio":
                    buffer.extend(mensaje.get("data", b""))
            if buffer:
                return bytes(buffer)
            time.sleep(2)
        except edge_tts.exceptions.NoAudioReceived:
            if intento == 2:
                raise
            time.sleep(3 * (intento + 1))
    return b""


def generar_audio(texto: str, voz: str, rate: str) -> bytes:
    try:
        return asyncio.run(generar_fragmento(texto, voz, rate))
    except Exception:
        return b""

# ---------------- Interfaz ----------------
col_config, col_main = st.columns([1, 3])

with col_config:
    st.markdown("### 🎚️ Nivel y voz")

    nivel = st.selectbox("📊 Nivel", list(LECCIONES.keys()))
    lecciones = LECCIONES[nivel]
    leccion_idx = st.selectbox(
        "📗 Lección", range(len(lecciones)),
        format_func=lambda i: lecciones[i]["titulo"])
    leccion = lecciones[leccion_idx]

    st.markdown("**🎤 Voz británica**")
    voz_nombre = st.selectbox("Voz", list(VOICES.keys()),
                              label_visibility="collapsed")

    velocidad = st.select_slider(
        "Velocidad", options=["-25%", "Normal", "+25%"], value="Normal")

    st.divider()
    st.markdown(
        "<p class='credit'>Diseñado con la IA por<br><b>Ing. Hernán Quiroz</b></p>",
        unsafe_allow_html=True)

with col_main:
    # ---- Cajita 1: párrafo en inglés ----
    st.markdown("<div class='card'><b>📖 Párrafo</b> — "
                "léelo y escúchalo en voz británica.</div>",
                unsafe_allow_html=True)
    st.markdown(f"#### {leccion['titulo']} · _{nivel}_")
    st.write(leccion["parrafo"])

    col_escuchar, col_espacio = st.columns([1, 2])
    if col_escuchar.button("🔊 Escuchar párrafo", use_container_width=True):
        rate = "-25%" if velocidad == "-25%" else "+25%" if velocidad == "+25%" else "+0%"
        with st.spinner("Generando audio..."):
            audio = generar_audio(leccion["parrafo"], VOICES[voz_nombre], rate)
        if audio:
            st.audio(audio, format="audio/mp3")
        else:
            st.error("No se pudo generar el audio. Prueba otra voz.")

    st.divider()

    # ---- Cajita 2: escritura del resumen ----
    st.markdown("<div class='card'><b>✍️ Tu resumen</b> — escribe en inglés "
                "un resumen del párrafo. Al enviarlo, el sistema marcará "
                "errores de ortografía y gramática (inglés británico).</div>",
                unsafe_allow_html=True)
    resumen = st.text_area("Escribe aquí tu resumen:", height=160,
                           key=f"resumen_{nivel}_{leccion_idx}")

    if st.button("📝 Revisar mi resumen", type="primary", use_container_width=True):
        if not resumen.strip():
            st.warning("Escribe tu resumen primero.")
        else:
            # 1) Corrección con LanguageTool
            with st.spinner("Revisando ortografía y gramática..."):
                try:
                    herramienta = obtener_correccion()
                    coincidencias = herramienta.check(resumen)
                except Exception as e:
                    coincidencias = []
                    st.error(f"No pude conectar con el corrector: {e}")

            if not coincidencias:
                st.success("🎉 ¡Perfecto! No encontré errores de ortografía "
                           "ni gramática en inglés británico.")
            else:
                st.warning(f"Encontré **{len(coincidencias)} problema(s)**. "
                           "Revisa cada sugerencia:")
                for i, c in enumerate(coincidencias, 1):
                    error = resumen[c.offset: c.offset + c.errorLength]
                    st.markdown(
                        f"**{i}.** 🚫 «{error}» → ✅ "
                        f"**{c.replacements[0] if c.replacements else '—'}** "
                        f"_({c.message})_")

            # 2) Análisis básico del resumen
            st.divider()
            palabras_usuario = {
                p.strip(".,;:!?()'\"").lower() for p in resumen.split()}
            palabras_parrafo = {
                p.strip(".,;:!?()'\"").lower() for p in leccion["parrafo"].split()}
            claves = palabras_usuario & palabras_parrafo
            st.markdown(
                f"📊 **Análisis:** escribiste **{len(resumen.split())} palabras** "
                f"y usaste **{len(claves)}** términos clave del párrafo "
                "(original, sin conjugar).")
            longitud = len(resumen.split())
            if longitud < 15:
                st.info("💡 Intenta resumir con al menos 15–20 palabras para "
                        "practicar más.")
            else:
                st.info("💡 Buen trabajo. Compara tu resumen con el párrafo "
                        "y escucha de nuevo el audio para mejorar tu fluidez.")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>🎓 Learn British English — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
