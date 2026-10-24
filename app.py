import asyncio
import time

import edge_tts
import language_tool_python
import streamlit as st

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
      <p>De cero (A1) hasta C2 — lee, escucha, escribe y recibe correcciones.</p>
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

# ---------------- Estado de sesión ----------------
ss = st.session_state
if "resumen_visto" not in ss:
    ss.resumen_visto = None  # (nivel, leccion_idx) cuyo resultado mostrar

# ---------------- Utilidades ----------------
@st.cache_resource
def obtener_correccion():
    """LanguageTool en inglés británico (sin API key)."""
    return language_tool_python.LanguageTool("en-GB")


async def generar_fragmento(texto: str, voz: str, rate: str) -> bytes:
    """Genera el audio de un fragmento con reintentos (evita fallos 429)."""
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


def dividir_en_fragmentos(texto: str, maximo: int = 2500) -> list:
    trozos, actual = [], ""
    for linea in texto.splitlines():
        if len(actual) + len(linea) + 1 > maximo:
            if actual.strip():
                trozos.append(actual)
            actual = linea
        else:
            actual += "\n" + linea
    if actual.strip():
        trozos.append(actual)
    return trozos

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

    col_escuchar, col_dlc = st.columns([1, 1])
    if col_escuchar.button("🔊 Escuchar párrafo", use_container_width=True):
        rate = ("-25%" if velocidad == "-25%"
                else "+25%" if velocidad == "+25%" else "+0%")
        with st.spinner("Generando audio..."):
            audio = generar_audio(leccion["parrafo"], VOICES[voz_nombre], rate)
        if audio:
            st.audio(audio, format="audio/mp3")
        else:
            st.error("No se pudo generar el audio. Prueba otra voz.")

    st.divider()

    # ---- Cajita 2: escritura del resumen ----
    st.markdown("<div class='card'><b>✍️ Tu resumen</b> — escribe en inglés "
                "un resumen del párrafo. Al revisarlo, el sistema marcará "
                "errores de ortografía y gramática (inglés británico).</div>",
                unsafe_allow_html=True)

    clave_actual = (nivel, leccion_idx)
    resumen = st.text_area(
        "Escribe aquí tu resumen:", height=160,
        key=f"resumen_{nivel}_{leccion_idx}")

    # Mostrar resultado guardado si el usuario cambió de lección
    if ss.resumen_visto is not None and ss.resumen_visto != clave_actual:
        ss.resumen_visto = None

    if st.button("📝 Revisar mi resumen", type="primary",
                 use_container_width=True):
        if not resumen.strip():
            st.warning("Escribe tu resumen primero.")
        else:
            # 1) Corrección con LanguageTool (en-GB)
            with st.spinner("Revisando ortografía y gramática..."):
                try:
                    herramienta = obtener_correccion()
                    coincidencias = herramienta.check(resumen)
                except Exception as e:
                    coincidencias = []
                    st.error(f"No pude conectar con el corrector: {e}")

            st.session_state["resultado"] = {
                "clase": "ok" if not coincidencias else "errores",
                "coincidencias": [
                    {"error": resumen[c.offset: c.offset + c.errorLength],
                     "sugerencia": c.replacements[0] if c.replacements else "—",
                     "mensaje": c.message}
                    for c in coincidencias
                ],
                "n_palabras": len(resumen.split()),
                "claves": len({
                    p.strip(".,;:!?()'\"").lower()
                    for p in resumen.split()
                } & {
                    p.strip(".,;:!?()'\"").lower()
                    for p in leccion["parrafo"].split()
                }),
            }
            ss.resumen_visto = clave_actual
            st.rerun()

    # Mostrar el resultado de la revisión
    resultado = st.session_state.get("resultado")
    if resultado and ss.resumen_visto == clave_actual:
        if resultado["clase"] == "ok":
            st.success("🎉 ¡Perfecto! No encontré errores de ortografía "
                       "ni gramática en inglés británico.")
        else:
            st.warning(f"Encontré **{len(resultado['coincidencias'])} "
                       "problema(s)**. Revisa cada sugerencia:")
            for i, c in enumerate(resultado["coincidencias"], 1):
                st.markdown(
                    f"**{i}.** 🚫 «{c['error']}» → ✅ **{c['sugerencia']}** "
                    f"_({c['mensaje']})_")

        st.divider()
        st.markdown(
            f"📊 **Análisis:** escribiste **{resultado['n_palabras']} palabras** "
            f"y usaste **{resultado['claves']}** términos clave del párrafo.")
        if resultado["n_palabras"] < 15:
            st.info("💡 Intenta resumir con al menos 15–20 palabras para "
                    "practicar más.")
        else:
            st.info("💡 Buen trabajo. Escucha de nuevo el audio para mejorar "
                    "tu fluidez.")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>🎓 Learn British English — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
