import os
import time
import streamlit as st
from pypdf import PdfReader
from google import genai

# 1. Page Configuration (यूजर इंटरफेस सेटिंग्स)
st.set_page_config(page_title="AI Syllabus Mapper", page_icon="📚", layout="wide")

st.title("📚 AI Syllabus & PYP Chapter Mapper")
st.write("अपनी Syllabus और PYP (Previous Year Paper) PDF अपलोड करें और AI से चैप्टर-वाइज मैपिंग करवाएं।")

# 2. API Key Configuration
# सुरक्षा के लिए API Key को Streamlit के Secrets (Environment) से लोड करना सबसे बेस्ट है
API_KEY = st.sidebar.text_input("Enter Gemini API Key", type="password", value=os.getenv("GENAI_API_KEY", ""))

if not API_KEY:
    st.info("💡 कृपया बाईं तरफ (Sidebar) अपनी Gemini API Key दर्ज करें या `GENAI_API_KEY` सेट करें।")
    st.stop()

# Client Initialize करना
try:
    client = genai.Client(api_key=API_KEY)
except Exception as e:
    st.error(f"API क्लाइंट इनिशियलाइजेशन फेल: {str(e)}")
    st.stop()

# 3. PDF से टेक्स्ट निकालने का हेल्पर फ़ंक्शन
def extract_text_from_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text.strip()
    except Exception as e:
        st.error(f"PDF पढ़ने में त्रुटि: {str(e)}")
        return ""

# 4. बड़े टेक्स्ट को छोटे हिस्सों (Chunks) में बांटना
def chunk_text(text, max_chars=8000):
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        add_len = len(line) + 1
        if current_len + add_len <= max_chars:
            current.append(line)
            current_len += add_len
        else:
            if current:
                chunks.append("\n".join(current))
            current = [line]
            current_len = add_len
    if current:
        chunks.append("\n".join(current))
    return chunks

# 5. Gemini AI को कॉल करने का फ़ंक्शन (Retry Logic के साथ)
def call_gemini(prompt, model_name="gemini-1.5-flash"):
    try:
        resp = client.models.generate_content(model=model_name, contents=prompt)
        if hasattr(resp, "text"):
            return resp.text
        return str(resp)
    except Exception as e:
        # अगर Rate Limit (429) एरर आए तो थोड़ा रुककर दोबारा प्रयास करें
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            st.warning("⚠️ Rate limit आ गई है, 15 सेकंड का ब्रेक ले रहे हैं...")
            time.sleep(15)
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt)
                return resp.text if hasattr(resp, "text") else str(resp)
            except Exception as retry_e:
                st.error(f"दुबारा प्रयास भी फेल हुआ: {str(retry_e)}")
                return None
        else:
            st.error(f"AI कॉल एरर: {str(e)}")
            return None

# ==========================================
# 6. WEBSITE WEB-UI & CORE FLOW
# ==========================================

# दो कॉलम लेआउट फाइल्स अपलोड करने के लिए
col1, col2 = st.columns(2)

with col1:
    syllabus_file = st.file_uploader("1. Syllabus PDF अपलोड करें", type=["pdf"])

with col2:
    pyp_file = st.file_uploader("2. PYP Paper PDF अपलोड करें", type=["pdf"])

# प्रोसेसिंग बटन
if st.button("🚀 Start AI Analysis & Mapping", type="primary"):
    if not syllabus_file or not pyp_file:
        st.error("❌ कृपया दोनों PDF फाइलें (Syllabus और PYP) अपलोड करें!")
    else:
        with st.spinner("⏳ स्टेप 1: पीडीएफ फाइलों से टेक्स्ट निकाला जा रहा है..."):
            raw_sys_text = extract_text_from_pdf(syllabus_file)
            raw_pyp_text = extract_text_from_pdf(pyp_file)

        if not raw_sys_text or not raw_pyp_text:
            st.error("❌ पीडीएफ से टेक्स्ट नहीं निकाला जा सका। कृपया चेक करें कि पीडीएफ स्कैन की हुई इमेज तो नहीं है।")
        else:
            st.success("✅ दोनों पीडीएफ का टेक्स्ट सफलतापूर्वक लोड हो गया है।")
            
            # स्टेप 2: सिलेबस स्ट्रक्चर बनाना
            with st.spinner("⏳ स्टेप 2: AI सिलेबस का स्ट्रक्चर समझ रहा है..."):
                struct_prompt = (
                    "Analyze this raw syllabus text and extract ONLY the hierarchical structure of Subjects and Chapters. "
                    "Remove all descriptive fluff or paragraphs. Output it as a clean list of 'Subject -> Chapter'.\n\n"
                    f"Raw Syllabus:\n{raw_sys_text}"
                )
                optimized_sys_structure = call_gemini(struct_prompt)
            
            if not optimized_sys_structure:
                optimized_sys_structure = raw_sys_text
                st.warning("⚠️ सिलेबस स्ट्रक्चर ऑप्टिमाइज़ नहीं हो सका, डायरेक्ट टेक्स्ट का उपयोग कर रहे हैं।")
            else:
                st.success("✅ सिलेबस का चैप्टर-वाइज स्ट्रक्चर तैयार है।")
            
            # स्टेप 3: PYP को मैप करना
            st.info("⏳ स्टेप 3: AI आपके पेपर के सवालों को सिलेबस के चैप्टर्स के साथ मैप कर रहा है...")
            pyp_chunks = chunk_text(raw_pyp_text)
            combined_output = ""
            
            # प्रोग्रेस बार यूजर को दिखाने के लिए
            progress_bar = st.progress(0)
            
            for idx, p_chunk in enumerate(pyp_chunks):
                st.write(f"🔄 भाग [{idx+1}/{len(pyp_chunks)}] प्रोसेस हो रहा है...")
                
                prompt = (
                    "You are a strict academic data processor. Your task is Chapter-wise Question Mapping.\n\n"
                    "CRITICAL RULES:\n"
                    "1. Never change the order of Subjects and Chapters.\n"
                    "2. Do not rewrite or omit any chapter name.\n"
                    "3. For every question in the PYP segment, identify the matching Chapter.\n"
                    "4. Append the question number and full original question under that chapter header.\n"
                    "5. Output must be in Hindi.\n\n"
                    f"--- SYLLABUS REFERENCE STRUCTURE ---\n{optimized_sys_structure}\n\n"
                    f"--- PYP MCQ SEGMENT ---\n{p_chunk}"
                )
                
                chunk_resp = call_gemini(prompt)
                if chunk_resp:
                    combined_output += chunk_resp + "\n\n"
                
                # प्रोग्रेस अपडेट करना
                progress_bar.progress((idx + 1) / len(pyp_chunks))
                
                # फ्री टियर ब्लॉकिंग से बचने के लिए छोटा सा डिले
                time.sleep(3)
            
            # स्टेप 4: फाइनल रिजल्ट दिखाना और डाउनलोड देना
            if combined_output.strip():
                st.success("🎉 बधाई हो! आपका चैप्टर-वाइज एनालिसिस 100% पूरा हो गया है।")
                
                # रिजल्ट को वेबसाइट पर दिखाना
                st.subheader("📋 AI Mapped Result Preview:")
                st.text_area("Output Text", value=combined_output, height=400)
                
                # डायरेक्ट डाउनलोड बटन (.txt फाइल के लिए)
                st.download_button(
                    label="📥 Download Mapped Output File",
                    data=combined_output,
                    file_name="pyp_chapterwise_mapped_output.txt",
                    mime="text/plain"
                )
            else:
                st.error("❌ AI से कोई वैध डेटा मैप होकर नहीं मिल पाया।")
