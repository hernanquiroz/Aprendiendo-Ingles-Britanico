import asyncio
import json
import os
import re
import time

import edge_tts
import language_tool_python
import requests
import streamlit as st
from audio_recorder_streamlit import audio_recorder

from lessons import LECCIONES

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
      .credit b { font-size: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>🇬🇧 Learn British English</h1>
      <p>De cero (A1) hasta C2 — lee, escucha, escribe, habla y recibe feedback inteligente.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Voces británicas ----------------
VOICES = {
    "🇬🇧 Voz masculina (Ryan)": "en-GB-RyanNeural",
    "🇬🇧 Voz masculina (Thomas)": "en-GB-ThomasNeural",
    "🇬🇧 Voz femenina (Sonia)": "en-GB-SoniaNeural",
    "🇬🇧 Voz femenina (Libby)": "en-GB-LibbyNeural",
}

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3"

# ---------------- Estado de sesión ----------------
ss = st.session_state
if "resumen_visto" not in ss:
    ss.resumen_visto = None

# ---------------- Utilidades ----------------
@st.cache_resource
def obtener_correccion():
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


def obtener_api_key() -> str:
    return (st.secrets.get("LLM_API_KEY") if "LLM_API_KEY" in st.secrets
            else os.environ.get("LLM_API_KEY", ""))


def evaluar_resumen_llm(parrafo: str, resumen: str, nivel: str):
    api_key = obtener_api_key()
    if not api_key:
        return {"error": "API key no encontrada. Verifica LLM_API_KEY en "
                         "Settings → Secrets y reinicia la app."}

    system = (
        "You are a British English teacher assessing a summary. "
        "Reply ONLY with valid JSON in Spanish explanations, with these keys: "
        '{"nota": <number 0-10>, '
        '"captura_ideas": <list of main ideas present in the summary>, '
        '"ideas_faltantes": <list of important ideas missing from the summary>, '
        '"vocabulario": <one short sentence assessing vocabulary level vs the '
        "target level>, "
        '"sugerencias": <list of 2-4 concrete suggestions to improve, each '
        "with an English example>}"
    )
    user_msg = (f"Nivel objetivo: {nivel}\n\nPárrafo original:\n{parrafo}\n\n"
                f"Resumen del estudiante:\n{resumen}")

    try:
        respuesta = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        if respuesta.status_code != 200:
            return {"error": f"Groq respondió {respuesta.status_code}: "
                             f"{respuesta.text[:300]}"}
        contenido = respuesta.json()["choices"][0]["message"]["content"]
        return json.loads(contenido)
    except requests.exceptions.Timeout:
        return {"error": "La petición a Groq tardó demasiado (timeout)."}
    except json.JSONDecodeError:
        return {"error": "Groq devolvió una respuesta no válida en JSON."}
    except Exception as e:
        return {"error": f"Error inesperado: {e}"}


def transcribir_audio_groq(audio_bytes: bytes) -> dict:
    """Transcribe la grabación con Whisper (Groq). Devuelve texto o error."""
    api_key = obtener_api_key()
    if not api_key:
        return {"error": "API key no encontrada."}
    try:
        respuesta = requests.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("grabacion.webm", audio_bytes, "audio/webm")},
            data={"model": WHISPER_MODEL, "language": "en",
                  "response_format": "json"},
            timeout=120,
        )
        if respuesta.status_code != 200:
            return {"error": f"Whisper respondió {respuesta.status_code}: "
                             f"{respuesta.text[:300]}"}
        return {"texto": respuesta.json().get("text", "")}
    except requests.exceptions.Timeout:
        return {"error": "La transcripción tardó demasiado. Prueba con una "
                         "grabación más corta."}
    except Exception as e:
        return {"error": f"Error inesperado: {e}"}


def normalizar_palabras(texto: str) -> list:
    """Convierte el texto en lista de palabras limpias (minúsculas)."""
    return [p for p in re.split(r"[^a-zA-Z']+", texto.lower()) if p]


def comparar_pronunciacion(objetivo: str, dicho: str) -> dict:
    """Compara lo que dijiste con el texto objetivo, palabra por palabra."""
    palabras_objetivo = normalizar_palabras(objetivo)
    palabras_dichas = normalizar_palabras(dicho)

    #conteo para detectar omitidas y extra
    from collections import Counter
    cuenta_objetivo = Counter(palabras_objetivo)
    cuenta_dichas = Counter(palabras_dichas)

    correctas = cuenta_objetivo & cuenta_dichas     # intersección (mínimos)
    omitidas = cuenta_objetivo - correctas           # faltaron por decir
    extras = cuenta_dichas - correctas                # dijiste de más

    n_total = len(palabras_objetivo)
    n_correctas = sum(correctas.values())
    precision = round(100 * n_correctas / n_total, 1) if n_total else 0

    return {
        "precision": precision,
        "correctas": list(correctas.elements()),
        "omitidas": list(omitidas.elements()),
        "extras": list(extras.elements()),
        "n_objetivo": n_total,
        "n_dichas": len(palabras_dichas),
    }

# ---------------- Interfaz ----------------
col_config, col_main = st.columns([1, 3])

with col_config:
    st.markdown("### 🎚️ Nivel y voz")

    nivel = st.selectbox("📊 Nivel", list(LECCIONES.keys()))
    lecciones = LECCIONES[nivel]
    leccion_idx = st.selectbox(
        "📗 Lección", range(len(lecciones)),
        format_func=lambda i: f"{i + 1}. {lecciones[i]['titulo']}")
    leccion = lecciones[leccion_idx]

    st.markdown("**🎤 Voz británica**")
    voz_nombre = st.selectbox("Voz", list(VOICES.keys()),
                              label_visibility="collapsed")

    velocidad = st.select_slider(
        "Velocidad", options=["-25%", "Normal", "+25%"], value="Normal")

    st.divider()
    st.markdown("#### 📚 Progreso")
    st.metric("Lecciones", f"{leccion_idx + 1} de {len(lecciones)}")

    if obtener_api_key():
        st.caption("🤖 Feedback inteligente: activo")
    else:
        st.warning("⚠️ Añade tu LLM_API_KEY en Secrets.")

    st.divider()
    st.markdown(
        "<p class='credit'>Diseñado con la IA por<br><b>Ing. Hernán Quiroz</b></p>",
        unsafe_allow_html=True)

with col_main:
    # ---- Cajita 1: párrafo ----
    st.markdown("<div class='card'><b>📖 Párrafo</b> — léelo, escúchalo en "
                "voz británica y practica hablarlo.</div>",
                unsafe_allow_html=True)
    st.markdown(f"#### {leccion['titulo']} · _{nivel}_")
    st.write(leccion["parrafo"])

    if st.button("🔊 Escuchar párrafo (voz nativa)", use_container_width=True):
        rate = ("-25%" if velocidad == "-25%"
                else "+25%" if velocidad == "+25%" else "+0%")
        with st.spinner("Generando audio..."):
            audio = generar_audio(leccion["parrafo"], VOICES[voz_nombre], rate)
        if audio:
            st.audio(audio, format="audio/mp3")
        else:
            st.error("No se pudo generar el audio. Prueba otra voz.")

    st.divider()

    # ---- Cajita 3: hablar y corrección de pronunciación ----
    st.markdown("<div class='card'><b>🎤 Practica hablando</b> — pulsa el "
                "micrófono y lee el párrafo en voz alta. El sistema "
                "transcribirá lo que dijiste y comparará palabra por "
                "palabra.</div>", unsafe_allow_html=True)

    grabacion = audio_recorder(
        text="", recording_color="#C8102E", neutral_color="#012169",
        icon_size="2x", key=f"rec_{nivel}_{leccion_idx}")

    if grabacion is not None and len(grabacion) > 0:
        st.markdown("**🎧 Tu grabación:**")
        st.audio(grabacion, format="audio/webm")

        if st.button("🤓 Analizar mi pronunciación", type="primary",
                     use_container_width=True, key="analizar_habla"):
            with st.spinner("Transcribiendo con Whisper..."):
                resultado_transcripcion = transcribir_audio_groq(grabacion)

            if "error" in resultado_transcripcion:
                st.error(f"**Transcripción falló:** "
                         f"{resultado_transcripcion['error']}")
            else:
                texto_dicho = resultado_transcripcion["texto"]
                comparacion = comparar_pronunciacion(
                    leccion["parrafo"], texto_dicho)

                st.session_state["habla_resultado"] = {
                    "clave": (nivel, leccion_idx),
                    "transcripcion": texto_dicho,
                    "comparacion": comparacion,
                }

    # Mostrar resultado del habla
    habla = st.session_state.get("habla_resultado")
    if habla and habla["clave"] == (nivel, leccion_idx):
        comp = habla["comparacion"]
        st.divider()
        st.markdown("## 🤓 Resultado de tu habla")

        precision = comp["precision"]
        if precision >= 90:
            st.success(f"### 🏆 Precisión: **{precision}%** — ¡Prácticamente "
                       "perfecta!")
        elif precision >= 70:
            st.warning(f"### 🏆 Precisión: **{precision}%** — Muy bien, "
                       "sigue puliendo las palabras marcadas.")
        else:
            st.error(f"### 🏆 Precisión: **{precision}%** — Escucha el audio "
                     "nativo y repite con calma.")

        st.markdown(f"**Lo que entendí que dijiste:**")
        st.info(f"«{habla['transcripcion']}»")

        col_bien, col_mal = st.columns(2)
        with col_bien:
            st.markdown(f"**✅ Palabras correctas** ({len(comp['correctas'])} "
                        f"de {comp['n_objetivo']}):")
            if comp["correctas"]:
                st.markdown(" ".join(f"`{p}`" for p in comp["correctas"]))
        with col_mal:
            st.markdown(f"**❌ Palabras omitidas o mal pronunciadas** "
                        f"({len(comp['omitidas'])}):")
            if comp["omitidas"]:
                st.markdown(" ".join(f"`{p}`" for p in comp["omitidas"]))
            else:
                st.markdown("Ninguna — ¡brillante! 🎉")

        if comp["extras"]:
            with st.expander("ℹ️ Palabras extra detectadas"):
                st.markdown(" ".join(f"`{p}`" for p in comp["extras"]))

        st.info("💡 Consejo: escucha el audio nativo, repite las palabras "
                "omitidas en voz alta y graba de nuevo para mejorar tu "
                "puntuación.")

    st.divider()

    # ---- Cajita 2: resumen ----
    st.markdown("<div class='card'><b>✍️ Tu resumen</b> — escribe en inglés "
                "un resumen del párrafo. Recibirás corrección ortográfica, "
                "gramatical y feedback pedagógico inteligente.</div>",
                unsafe_allow_html=True)

    clave_actual = (nivel, leccion_idx)
    resumen = st.text_area(
        "Escribe aquí tu resumen:", height=160,
        key=f"resumen_{nivel}_{leccion_idx}")

    if ss.resumen_visto is not None and ss.resumen_visto != clave_actual:
        ss.resumen_visto = None

    if st.button("📝 Revisar mi resumen", type="primary",
                 use_container_width=True, key="revisar_resumen"):
        if not resumen.strip():
            st.warning("Escribe tu resumen primero.")
        else:
            with st.spinner("Revisando ortografía y gramática..."):
                try:
                    herramienta = obtener_correccion()
                    coincidencias = herramienta.check(resumen)
                except Exception:
                    coincidencias = []

            st.session_state["resultado"] = {
                "coincidencias": [
                    {"error": resumen[c.offset: c.offset + c.errorLength],
                     "sugerencia": c.replacements[0] if c.replacements else "—",
                     "mensaje": c.message}
                    for c in coincidencias
                ],
                "n_palabras": len(resumen.split()),
                "claves": len({
                    p.strip(".,;:!?()'\"").lower() for p in resumen.split()
                } & {
                    p.strip(".,;:!?()'\"").lower()
                    for p in leccion["parrafo"].split()
                }),
            }
            ss.resumen_visto = clave_actual

            with st.spinner("🤖 Analizando tu resumen..."):
                st.session_state["feedback"] = evaluar_resumen_llm(
                    leccion["parrafo"], resumen, nivel)
            st.rerun()

    # ---- Resultado del resumen ----
    resultado = st.session_state.get("resultado")
    feedback = st.session_state.get("feedback")
    if resultado and ss.resumen_visto == clave_actual:

        if not resultado["coincidencias"]:
            st.success("🎉 ¡Perfecto! No encontré errores de ortografía ni "
                       "gramática en inglés británico.")
        else:
            st.warning(f"Encontré **{len(resultado['coincidencias'])} "
                       "problema(s)**. Revisa cada sugerencia:")
            for i, c in enumerate(resultado["coincidencias"], 1):
                st.markdown(f"**{i}.** 🚫 «{c['error']}» → ✅ "
                            f"**{c['sugerencia']}** _({c['mensaje']})_")

        st.divider()

        if feedback is None:
            st.info("ℹ️ Feedback inteligente no disponible.")
        elif "error" in feedback:
            st.error(f"🤖 **Feedback inteligente falló:** {feedback['error']}")
        else:
            st.markdown("## 🤖 Feedback del profesor")

            nota = feedback.get("nota")
            if nota is not None:
                if nota >= 8:
                    st.success(f"### ⭐ Nota: **{nota}/10** — ¡Excelente trabajo!")
                elif nota >= 5:
                    st.warning(f"### ⭐ Nota: **{nota}/10** — Vas bien, "
                               "con detalles por pulir.")
                else:
                    st.error(f"### ⭐ Nota: **{nota}/10** — Repasa el párrafo "
                             "e inténtalo de nuevo.")

            col_ok, col_falta = st.columns(2)
            with col_ok:
                capturadas = feedback.get("captura_ideas", [])
                st.markdown(f"**✅ Ideas capturadas** ({len(capturadas)}):")
                for idea in capturadas:
                    st.markdown(f"- ✔️ {idea}")
            with col_falta:
                faltantes = feedback.get("ideas_faltantes", [])
                st.markdown(f"**❗ Ideas que faltan** ({len(faltantes)}):")
                for idea in faltantes:
                    st.markdown(f"- ➕ {idea}")

            if feedback.get("vocabulario"):
                st.markdown(f"**🗣️ Vocabulario:** {feedback['vocabulario']}")

            sugerencias = feedback.get("sugerencias", [])
            if sugerencias:
                st.markdown("**💡 Sugerencias para mejorar:**")
                for s in sugerencias:
                    st.markdown(f"- 💡 {s}")

        st.divider()
        st.markdown(
            f"📊 **Análisis:** escribiste **{resultado['n_palabras']} palabras** "
            f"y usaste **{resultado['claves']}** términos clave del párrafo.")
        if resultado["n_palabras"] < 15:
            st.info("💡 Intenta resumir con al menos 15–20 palabras para "
                    "practicar más.")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>🎓 Learn British English — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
