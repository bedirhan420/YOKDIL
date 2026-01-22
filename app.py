import streamlit as st
import os
import json
import random
import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- 1. FIREBASE VE AYARLAR ---
if not firebase_admin._apps:
    if "FIREBASE_JSON" in st.secrets:
        # Streamlit Secrets TOML formatında olduğu için doğrudan dict olarak alabiliriz
        firebase_info = dict(st.secrets["FIREBASE_JSON"])
        cred = credentials.Certificate(firebase_info)
    else:
        # Lokal çalışma için dosya yolu
        cred = credentials.Certificate("serviceAccountKey.json")
    
    firebase_admin.initialize_app(cred)

db = firestore.client()

current_dir = os.path.dirname(os.path.abspath(__file__))
JSON_FOLDER = os.path.join(current_dir, "YOKDIL_JSON_CIKTILAR")
WORDS_FILE = os.path.join(current_dir, "yokdil_words.json")
GRAMMAR_FILE = os.path.join(current_dir, "grammar_notes.json")

# --- 2. SESSION STATE YÖNETİMİ ---
states = {
    'user': None,
    'last_selected_file': None,
    'master_words': None,
    'word_index': 0,
    'quiz_shuffled_options': None,
    'match_selected_word': None,
    'match_pairs': {},
    'match_shuffled_meanings': None,
    'match_sub_page': 0 # Eşleştirme için alt sayfa
}
for key, val in states.items():
    if key not in st.session_state: st.session_state[key] = val

st.set_page_config(page_title="YÖKDİL Hazırlık Portalı", layout="wide", initial_sidebar_state="expanded")

# --- 3. YARDIMCI FONKSİYONLAR ---
def format_text(text):
    if not text: return ""
    return " ".join(text.split())

# --- 4. GRAMER NOTLARI MODÜLÜ (Eksiksiz Okuma) ---
def grammar_app():
    st.title("📖 YÖKDİL Gramer Notları")
    
    if not os.path.exists(GRAMMAR_FILE):
        st.error("grammar_notes.json bulunamadı! Lütfen dosyayı ana dizine ekleyin.")
        return

    with open(GRAMMAR_FILE, "r", encoding="utf-8") as f:
        grammar_data = json.load(f)

    # Sidebar: Konu Seçimi
    konu_listesi = list(grammar_data.keys())
    secilen_konu = st.sidebar.selectbox("Gramer Konusu Seçin", konu_listesi)
    
    st.header(f"✨ {secilen_konu}")
    st.divider()

    # Alt konuları ve 367 satırlık içeriğin tamamını döngüye al
    for section in grammar_data[secilen_konu]:
        with st.expander(f"📘 {section.get('topic', 'Genel Kurallar')}", expanded=True):
            for item in section.get('content', []):
                # Başlık (Title)
                if "title" in item:
                    st.markdown(f"**📍 {item['title']}**")
                
                # Kural Metni (Mavi kutu)
                if "rule" in item:
                    st.info(item["rule"])
                
                # Formül Metni (Kod bloğu)
                if "formula" in item:
                    st.code(item["formula"], language="text")
                
                # Örnekler (PDF'teki → okunu koruyarak)
                if "examples" in item:
                    for ex in item["examples"]:
                        st.write(f"→ {ex}")
                st.write("") # Görsel boşluk
        st.divider()

# --- 5. ETKİNLİK MODÜLLERİ (KELİME ÇALIŞMA) ---

def flash_card_ui(word_data, is_learned):
    border_color = "#4CAF50" if is_learned else "#4F8BF9"
    st.markdown(f"""
        <div style="background-color: #1E1E1E; padding: 50px; border-radius: 15px; border: 3px solid {border_color}; text-align: center;">
            <h1 style="color: {border_color}; font-size: 65px; margin-bottom:0;">{word_data['word']}</h1>
            <p style="color: #888; font-size: 20px;">{word_data['type']} {'✅ [ÖĞRENİLDİ]' if is_learned else ''}</p>
        </div>
    """, unsafe_allow_html=True)

    st.write("")
    with st.expander("Anlamı, Eş ve Zıt Anlamları Gör"):
        col1, col2 = st.columns(2)
        with col1:
            st.info("🇹🇷 **Türkçe Karşılıklar**")
            for m in word_data['means']: st.write(f"• {m}")
        with col2:
            st.info("🔗 **Kelimeler Arası İlişki**")
            st.write(f"**Synonyms:** {', '.join(word_data['synonyms'])}")
            if word_data.get('antonyms'):
                st.write(f"**Antonyms:** {', '.join(word_data['antonyms'])}")

def writing_ui(word_data):
    target_word = word_data['word']
    st.info(f"Anlamı: **{', '.join(word_data['means'])}** ({word_data['type']})")
    user_input = st.text_input("Kelimeyi Yazın:", key=f"write_{target_word}").strip()
    
    display_hint = " ".join([char if i < len(user_input) and user_input[i].lower() == char.lower() else "_" for i, char in enumerate(target_word)])
    st.markdown(f"<h2 style='letter-spacing: 5px; text-align:center; font-family: monospace;'>{display_hint}</h2>", unsafe_allow_html=True)
    
    if user_input:
        if user_input.lower() == target_word.lower():
            st.success("Tebrikler! Doğru yazdınız. 🎯")
            st.balloons()
        else:
            st.error("Henüz doğru değil, devam edin...")

def multiple_choice_ui(word_data, current_set):
    st.subheader(f"**{word_data['word']}**")
    
    if st.session_state.quiz_shuffled_options is None:
        correct_ans = ", ".join(word_data['means'])
        others = [", ".join(w['means']) for w in current_set if w['word'] != word_data['word']]
        distractors = random.sample(others, min(3, len(others)))
        options = distractors + [correct_ans]
        random.shuffle(options)
        st.session_state.quiz_shuffled_options = options

    user_choice = st.radio("Seçenekler:", st.session_state.quiz_shuffled_options)
    
    if st.button("Kontrol Et"):
        if user_choice == ", ".join(word_data['means']):
            st.success("Doğru! 🎯")
        else:
            st.error(f"Yanlış. Doğru cevap: {', '.join(word_data['means'])}")

def matching_ui(current_set):
    st.subheader("🧩 Kelime - Anlam Eşleştirme")
    st.write("Her aşamada 5 kelime eşleştirin.")

    sub_size = 5
    start_i = st.session_state.match_sub_page * sub_size
    subset = current_set[start_i:start_i + sub_size]
    
    target_meanings = {w['word']: ", ".join(w['means']) for w in subset}
    
    if st.session_state.match_shuffled_meanings is None or st.session_state.get('last_sub_key') != f"sub_{st.session_state.match_sub_page}":
        m_list = list(target_meanings.values())
        random.shuffle(m_list)
        st.session_state.match_shuffled_meanings = m_list
        st.session_state.last_sub_key = f"sub_{st.session_state.match_sub_page}"

    st.info(f"Aşama {st.session_state.match_sub_page + 1} / 4")

    c1, c2 = st.columns(2)
    with c1:
        st.write("### Kelimeler")
        for word in target_meanings.keys():
            matched = word in st.session_state.match_pairs
            selected = st.session_state.match_selected_word == word
            if st.button(f"{word} ✅" if matched else word, key=f"match_w_{word}", 
                         disabled=matched, use_container_width=True, 
                         type="primary" if selected else "secondary"):
                st.session_state.match_selected_word = word
                st.rerun()
                
    with c2:
        st.write("### Anlamlar")
        for m in st.session_state.match_shuffled_meanings:
            matched_w = next((w for w, val in st.session_state.match_pairs.items() if val == m), None)
            if st.button(f"✅ {m}" if matched_w else m, key=f"match_m_{m[:20]}", 
                         disabled=matched_w is not None, use_container_width=True):
                if st.session_state.match_selected_word:
                    if m == target_meanings[st.session_state.match_selected_word]:
                        st.session_state.match_pairs[st.session_state.match_selected_word] = m
                        st.session_state.match_selected_word = None
                        st.toast("Doğru! 🟢")
                    else:
                        st.error("Yanlış eşleşme! 🔴")
                    st.rerun()
                else:
                    st.warning("Önce bir kelime seçin!")

    st.divider()
    nc1, nc2, nc3 = st.columns([1, 2, 1])
    with nc1:
        if st.button("⬅️ Önceki 5'li", disabled=st.session_state.match_sub_page == 0):
            st.session_state.match_sub_page -= 1
            st.session_state.match_shuffled_meanings = None
            st.rerun()
    with nc3:
        if st.button("Sonraki 5'li ➡️", disabled=st.session_state.match_sub_page >= 3):
            st.session_state.match_sub_page += 1
            st.session_state.match_shuffled_meanings = None
            st.rerun()

    if len(st.session_state.match_pairs) >= len(subset) and st.session_state.match_sub_page == 3:
        st.balloons()
        st.success("Tebrikler! Tüm paketi başarıyla tamamladın! 🎉")

# --- 6. KELİME UYGULAMASI (ANA) ---
def words_app():
    uid = st.session_state.user['uid']
    if not os.path.exists(WORDS_FILE):
        st.error("yokdil_words.json bulunamadı!")
        return

    if st.session_state.master_words is None:
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            raw_data.sort(key=lambda x: x['word'])
            random.seed(42)
            random.shuffle(raw_data)
            st.session_state.master_words = raw_data

    all_types = sorted(list(set(w['type'] for w in st.session_state.master_words)))
    selected_type = st.sidebar.selectbox("Kelime Türü Seçin", all_types)
    type_specific_words = [w for w in st.session_state.master_words if w['type'] == selected_type]
    
    page_size = 20
    total_pages = (len(type_specific_words) // page_size) + (1 if len(type_specific_words) % page_size > 0 else 0)
    st.sidebar.subheader(f"📦 {selected_type} Paketleri")
    selected_page = st.sidebar.number_input(f"Paket Seç", min_value=1, max_value=total_pages, value=1)
    
    activity = st.sidebar.radio("Etkinlik Seçin", ["Flash Card", "Yazma Alıştırması", "Çoktan Seçmeli", "Kelime Eşleştirme"])
    
    current_set = type_specific_words[(selected_page - 1) * page_size : selected_page * page_size]

    key = f"{selected_type}_{selected_page}_{activity}"
    if st.session_state.get("prev_key") != key:
        st.session_state.prev_key = key
        st.session_state.word_index = 0
        st.session_state.quiz_shuffled_options = None
        st.session_state.match_pairs = {}
        st.session_state.match_shuffled_meanings = None
        st.session_state.match_selected_word = None
        st.session_state.match_sub_page = 0

    if not current_set:
        st.warning("Bu pakette kelime bulunamadı.")
        return

    st.progress((st.session_state.word_index + 1) / len(current_set))
    st.write(f"**{selected_type}** | Paket {selected_page} | Kelime: {st.session_state.word_index + 1}/{len(current_set)}")

    word_data = current_set[st.session_state.word_index]
    word_ref = db.collection("users").document(uid).collection("learned_words").document(word_data['word'].lower().strip())
    is_learned = word_ref.get().exists

    if activity == "Flash Card":
        flash_card_ui(word_data, is_learned)
    elif activity == "Yazma Alıştırması":
        writing_ui(word_data)
    elif activity == "Çoktan Seçmeli":
        multiple_choice_ui(word_data, current_set)
    elif activity == "Kelime Eşleştirme":
        matching_ui(current_set)

    if activity != "Kelime Eşleştirme":
        st.write("")
        b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
        with b1:
            if st.button("⬅️ Önceki"):
                st.session_state.word_index = (st.session_state.word_index - 1) % len(current_set)
                st.session_state.quiz_shuffled_options = None; st.rerun()
        with b2:
            if st.button("✅ ÖĞRENDİM", use_container_width=True):
                word_ref.set({"learned": True, "type": selected_type})
                st.session_state.word_index = (st.session_state.word_index + 1) % len(current_set)
                st.session_state.quiz_shuffled_options = None; st.rerun()
        with b3:
            if st.button("❌ ÖĞRENMEDİM", use_container_width=True):
                word_ref.delete()
                st.session_state.word_index = (st.session_state.word_index + 1) % len(current_set)
                st.session_state.quiz_shuffled_options = None; st.rerun()
        with b4:
            if st.button("Sonraki ➡️"):
                st.session_state.word_index = (st.session_state.word_index + 1) % len(current_set)
                st.session_state.quiz_shuffled_options = None; st.rerun()

# --- 7. GİRİŞ / KAYIT EKRANI ---
def auth_ui():
    st.title("🛡️ YÖKDİL Hazırlık Portalı")
    tab1, tab2 = st.tabs(["Giriş Yap", "Hesap Oluştur"])
    with tab1:
        msg_placeholder = st.empty()
        with st.form("login_form"):
            le = st.text_input("E-posta")
            lp = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap"):
                try:
                    user = auth.get_user_by_email(le)
                    st.session_state.user = {'uid': user.uid, 'email': le}
                    msg_placeholder.success("Giriş başarılı!")
                    st.rerun()
                except Exception:
                    msg_placeholder.error("E-posta veya şifre hatalı.")
    with tab2:
        with st.form("reg_form"):
            re = st.text_input("E-posta"); rp = st.text_input("Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                try: 
                    auth.create_user(email=re, password=rp)
                    st.success("Hesap Oluşturuldu! Giriş yapabilirsiniz.")
                except Exception as e: st.error(f"Hata: {e}")

# --- 8. SINAV MODÜLÜ (TAM KORUNAN) ---
def exam_app():
    uid = st.session_state.user['uid']
    files = sorted([f for f in os.listdir(JSON_FOLDER) if f.endswith(".json")])
    clean = {f: f.replace(".json", "") for f in files}
    sel = st.sidebar.selectbox("Deneme Seç", files, format_func=lambda x: clean[x])
    
    if sel != st.session_state.last_selected_file:
        st.session_state.last_selected_file = sel
        st.components.v1.html("<script>window.parent.window.scrollTo(0,0);</script>", height=0)
        st.rerun()

    if sel:
        deneme_id = clean[sel]
        user_ref = db.collection("users").document(uid).collection("denemeler").document(deneme_id)
        saved = (user_ref.get().to_dict() or {}).get("answers", {})
        with open(os.path.join(JSON_FOLDER, sel), "r", encoding="utf-8") as f: 
            qs = json.load(f)
        
        st.title(f"✍️ {deneme_id}")
        for q_no, q_info in qs.items():
            st.subheader(f"Soru {q_no}")
            psg = q_info.get("passage", ""); q_txt = q_info.get("question", "")
            if "--- PASSAGE ---" in q_txt:
                parts = q_txt.split("--- QUESTION ---")
                extracted_psg = parts[0].replace("--- PASSAGE ---", "").strip()
                if not psg: psg = extracted_psg
                q_txt = parts[1].strip() if len(parts) > 1 else ""
            else:
                q_txt = q_txt.replace("--- QUESTION ---", "").strip()

            if psg:
                psg_cleaned = format_text(psg)
                target_blank = f"({q_no}) ----"
                if target_blank in psg_cleaned:
                    psg_cleaned = psg_cleaned.replace(target_blank, f"<b style='color:#FF4B4B; text-decoration:underline;'>{target_blank}</b>")
                st.markdown(f'<div style="background-color:#1E1E1E; padding:20px; border-radius:10px; border-left:5px solid #4F8BF9; font-size:18px; line-height:1.6; margin-bottom:20px;">{psg_cleaned}</div>', unsafe_allow_html=True)
            
            st.write("") 
            st.markdown(f"**{format_text(q_txt)}**")
            st.write("")

            opts = q_info.get("options", [])
            prev = saved.get(str(q_no))
            idx = next((i for i, o in enumerate(opts) if o.strip().startswith(str(prev))), None) if prev else None
            
            choice = st.radio("Cevap:", opts, key=f"r_{deneme_id}_{q_no}", index=idx)
            if choice:
                letter = choice[0]
                if prev != letter:
                    saved[str(q_no)] = letter
                    user_ref.set({"answers": saved}, merge=True)
                if letter == q_info["answer"]: st.success("✅ Doğru")
                else: st.error(f"❌ Yanlış! Cevap: {q_info['answer']}")
            st.divider()

# --- 9. ANA ÇALIŞTIRICI ---
if st.session_state.user is None:
    auth_ui()
else:
    mode = st.sidebar.radio("Ana Menü", ["📚 Deneme Çöz", "🗂️ Kelime Çalış", "📖 Gramer Notları"])
    if st.sidebar.button("🚪 Çıkış Yap"): 
        st.session_state.user = None
        st.rerun()
    
    if mode == "📚 Deneme Çöz":
        exam_app()
    elif mode == "🗂️ Kelime Çalış":
        words_app()
    elif mode == "📖 Gramer Notları":
        grammar_app()