import asyncio
import base64
import io
import json
import os
import re
import time
from collections import Counter
from datetime import datetime

import edge_tts
import language_tool_python
import numpy as np
import requests
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from streamlit_drawable_canvas import st_canvas

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
      <p>De cero (A1) hasta C2 — lee, escucha, escribe (teclado o mano) y habla.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Constantes ----------------
VOICES = {
    "🇬🇧 Voz masculina (Ryan)": "en-GB-RyanNeural",
    "🇬🇧 Voz masculina (Thomas)": "en-GB-ThomasNeural",
    "🇬🇧 Voz femenina (Sonia)": "en-GB-SoniaNeural",
    "🇬🇧 Voz femenina (Libby)": "en-GB-LibbyNeural",
}

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3"

# ---------------- Estado de sesión ----------------
ss = st.session_state
for clave, valor in {
    "resumen_visto": None,
    "progreso": {},        # {(nivel, idx): {"notas": [], "precisiones": []}}
}.items():
    if clave not in ss:
        ss[clave] = valor

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
        return {"error": "API key no encontrada en Secrets."}

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
        r = requests.post(GROQ_URL,
                          headers={"Authorization": f"Bearer {api_key}",
                                   "Content-Type": "application/json"},
                          json={"model": GROQ_MODEL,
                                "messages": [
                                    {"role": "system", "content": system},
                                    {"role": "user", "content": user_msg}],
                                "temperature": 0.3,
                                "response_format": {"type": "json_object"}},
                          timeout=60)
        if r.status_code != 200:
            return {"error": f"Groq {r.status_code}: {r.text[:300]}"}
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except requests.exceptions.Timeout:
        return {"error": "Timeout. Inténtalo de nuevo."}
    except json.JSONDecodeError:
        return {"error": "Respuesta JSON no válida."}
    except Exception as e:
        return {"error": f"Error inesperado: {e}"}


def transcribir_audio_groq(audio_bytes: bytes) -> dict:
    api_key = obtener_api_key()
    if not api_key:
        return {"error": "API key no encontrada."}
    try:
        r = requests.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("grabacion.webm", audio_bytes, "audio/webm")},
            data={"model": WHISPER_MODEL, "language": "en",
                  "response_format": "json"},
            timeout=120)
        if r.status_code != 200:
            return {"error": f"Whisper {r.status_code}: {r.text[:300]}"}
        return {"texto": r.json().get("text", "")}
    except Exception as e:
        return {"error": f"Error inesperado: {e}"}


def normalizar_palabras(texto: str) -> list:
    return [p for p in re.split(r"[^a-zA-Z']+", texto.lower()) if p]


def comparar_pronunciacion(objetivo: str, dicho: str) -> dict:
    obj, dic = normalizar_palabras(objetivo), normalizar_palabras(dicho)
    c_obj, c_dic = Counter(obj), Counter(dic)
    correctas = c_obj & c_dic
    omitidas = c_obj - correctas
    extras = c_dic - correctas
    n_total = len(obj)
    n_ok = sum(correctas.values())
    return {"precision": round(100 * n_ok / n_total, 1) if n_total else 0,
            "correctas": list(correctas.elements()),
            "omitidas": list(omitidas.elements()),
            "extras": list(extras.elements()),
            "n_objetivo": n_total}


def transcribir_escritura_groq(imagen_png: bytes) -> dict:
    """OCR de escritura a mano con el modelo de visión de Groq."""
    api_key = obtener_api_key()
    if not api_key:
        return {"error": "API key no encontrada en Secrets."}
    b64 = base64.b64encode(imagen_png).decode()
    try:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": GROQ_VISION_MODEL,
                  "messages": [{"role": "user", "content": [
                      {"type": "text",
                       "text": "This is a photo of handwritten English text. "
                               "Transcribe the handwritten text exactly, with "
                               "correct English spelling. Reply ONLY with the "
                               "transcribed text, nothing else."},
                      {"type": "image_url",
                       "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
                  "temperature": 0},
            timeout=90)
        if r.status_code != 200:
            return {"error": f"OCR {r.status_code}: {r.text[:300]}"}
        return {"texto": r.json()["choices"][0]["message"]["content"].strip()}
    except requests.exceptions.Timeout:
        return {"error": "El OCR tardó demasiado. Escribe un poco menos y "
                         "prueba de nuevo."}
    except Exception as e:
        return {"error": f"Error inesperado: {e}"}


def registrar_progreso(clave, nota=None, precision=None):
    """Guarda un intento en el progreso (nota del resumen o precisión)."""
    ss.progreso.setdefault(clave, {"notas": [], "precisiones": []})
    if nota is not None:
        ss.progreso[clave]["notas"].append(nota)
    if precision is not None:
        ss.progreso[clave]["precisiones"].append(precision)

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

    # ---- Progreso ----
    st.markdown("#### 📈 Mi progreso")
    if ss.progreso:
        n_registros = sum(len(v["notas"]) + len(v["precisiones"])
                          for v in ss.progreso.values())
        st.metric("Intentos registrados", n_registros)
        with st.expander("Ver detalle"):
            for (niv, idx), datos in ss.progreso.items():
                titulo = LECCIONES[niv][idx]["titulo"]
                notas = datos["notas"]
                precs = datos["precisiones"]
                partes = [f"{titulo} ({niv})"]
                if notas:
                    partes.append(f"Resumen: {sum(notas)/len(notas):.1f}/10 "
                                  f"({len(notas)} intentos)")
                if precs:
                    partes.append(f"Habla: {sum(precs)/len(precs):.0f}% "
                                  f"({len(precs)} intentos)")
                st.markdown("- " + " · ".join(partes))

        # Exportar progreso
        progreso_json = json.dumps(
            {f"{k[0]}|{k[1]}": v for k, v in ss.progreso.items()},
            ensure_ascii=False)
        st.download_button("⬇️ Guardar progreso (JSON)", progreso_json,
                           "mi_progreso.json", "application/json",
                           use_container_width=True)
    else:
        st.caption("Aún no hay intentos registrados.")

    # Importar progreso
    archivo_progreso = st.file_uploader("📂 Restaurar progreso",
                                        type=["json"],
                                        key="import_progreso")
    if archivo_progreso is not None:
        try:
            datos = json.load(archivo_progreso)
            ss.progreso = {tuple(k.split("|")): v for k, v in datos.items()}
            ss.progreso = {(k[0], int(k[1])): v
                           for k, v in ss.progreso.items()}
            st.success("Progreso restaurado ✔️")
        except Exception:
            st.error("Archivo de progreso no válido.")

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

    # ---- Cajita 3: hablar ----
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
                res_trans = transcribir_audio_groq(grabacion)

            if "error" in res_trans:
                st.error(f"**Transcripción falló:** {res_trans['error']}")
            else:
                comp = comparar_pronunciacion(leccion["parrafo"],
                                              res_trans["texto"])
                registrar_progreso((nivel, leccion_idx),
                                    precision=comp["precision"])
                st.session_state["habla_resultado"] = {
                    "clave": (nivel, leccion_idx),
                    "transcripcion": res_trans["texto"],
                    "comparacion": comp}

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
        st.markdown("**Lo que entendí que dijiste:**")
        st.info(f"«{habla['transcripcion']}»")
        col_bien, col_mal = st.columns(2)
        with col_bien:
            st.markdown(f"**✅ Correctas** ({len(comp['correctas'])} de "
                        f"{comp['n_objetivo']}):")
            if comp["correctas"]:
                st.markdown(" ".join(f"`{p}`" for p in comp["correctas"]))
        with col_mal:
            st.markdown(f"**❌ Omitidas o mal pronunciadas** "
                        f"({len(comp['omitidas'])}):")
            if comp["omitidas"]:
                st.markdown(" ".join(f"`{p}`" for p in comp["omitidas"]))
            else:
                st.markdown("Ninguna — ¡brillante! 🎉")
        if comp["extras"]:
            with st.expander("ℹ️ Palabras extra detectadas"):
                st.markdown(" ".join(f"`{p}`" for p in comp["extras"]))

    st.divider()

    # ---- Cajita 2: resumen ----
    st.markdown("<div class='card'><b>✍️ Tu resumen</b> — escribe en inglés "
                "un resumen del párrafo con <b>teclado</b> o <b>a mano</b> "
                "(lápiz electrónico/touch). Recibirás corrección ortográfica, "
                "gramatical y feedback pedagógico inteligente.</div>",
                unsafe_allow_html=True)

    modo = st.radio("¿Cómo quieres escribir?", ["⌨️ Teclado", "✍️ A mano"],
                    horizontal=True, key="modo_escritura")

    resumen = ""
    if modo == "⌨️ Teclado":
        resumen = st.text_area("Escribe aquí tu resumen:", height=160,
                               key=f"resumen_{nivel}_{leccion_idx}")
    else:
        st.markdown("Escribe con el dedo, lápiz o mouse en el recuadro blanco:")
        canvas_result = st_canvas(
            fill_color="rgba(255,255,255,0)",
            stroke_width=3, stroke_color="#000000",
            background_color="#FFFFFF",
            height=250, drawing_mode="freedraw",
            key=f"canvas_{nivel}_{leccion_idx}")

        if st.button("🔍 Leer mi escritura (OCR)", use_container_width=True,
                     key="ocr_btn"):
            if canvas_result.image_data is not None:
                from PIL import Image
                img = Image.fromarray(
                    canvas_result.image_data.astype("uint8"))
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                with st.spinner("Reconociendo tu escritura..."):
                    res_ocr = transcribir_escritura_groq(buffer.getvalue())
                if "error" in res_ocr:
                    st.error(f"**OCR falló:** {res_ocr['error']}")
                else:
                    st.session_state["ocr_texto"] = res_ocr["texto"]
                    st.rerun()
            else:
                st.warning("Escribe algo primero en el recuadro.")

        if "ocr_texto" in st.session_state:
            st.success("🤖 **Texto reconocido:**")
            st.markdown(f"> {st.session_state['ocr_texto']}")
            st.caption("Revísalo y córregelo antes de enviarlo al revisor.")
            resumen = st.text_area(
                "Edita si es necesario y luego revisa:",
                value=st.session_state["ocr_texto"], height=140,
                key=f"resumen_ocr_{nivel}_{leccion_idx}")

    clave_actual = (nivel, leccion_idx)
    if ss.resumen_visto is not None and ss.resumen_visto != clave_actual:
        ss.resumen_visto = None

    if st.button("📝 Revisar mi resumen", type="primary",
                 use_container_width=True, key="revisar_resumen"):
        if not resumen.strip():
            st.warning("Escribe tu resumen primero.")
        else:
            with st.spinner("Revisando ortografía y gramática..."):
                try:
                    coincidencias = obtener_correccion().check(resumen)
                except Exception:
                    coincidencias = []

            st.session_state["resultado"] = {
                "coincidencias": [
                    {"error": resumen[c.offset: c.offset + c.errorLength],
                     "sugerencia": c.replacements[0] if c.replacements else "—",
                     "mensaje": c.message}
                    for c in coincidencias],
                "n_palabras": len(resumen.split()),
                "claves": len({
                    p.strip(".,;:!?()'\"").lower() for p in resumen.split()
                } & {
                    p.strip(".,;:!?()'\"").lower()
                    for p in leccion["parrafo"].split()}),
            }
            ss.resumen_visto = clave_actual

            with st.spinner("🤖 Analizando tu resumen..."):
                st.session_state["feedback"] = evaluar_resumen_llm(
                    leccion["parrafo"], resumen, nivel)

            # Registrar la nota en el progreso
            fb = st.session_state.get("feedback")
            if fb and "nota" in fb:
                registrar_progreso(clave_actual, nota=fb["nota"])
            st.rerun()

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
            st.info("💡 Intenta resumir con al menos 15–20 palabras.")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>🎓 Learn British English — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
