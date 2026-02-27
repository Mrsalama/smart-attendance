import streamlit as st
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
from deepface import DeepFace
from geopy.distance import geodesic
import tempfile
import os

# 1. إعداد الاتصال بـ Supabase من خلال الـ Secrets
try:
    URL = st.secrets["SUPABASE_URL"].strip()
    KEY = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(URL, KEY)
except Exception as e:
    st.error("⚠️ فشل في قراءة المفاتيح. تأكد من إضافتها في Streamlit Secrets.")
    st.stop()

def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

# --- واجهة التطبيق ---
st.set_page_config(page_title="نظام الحضور الذكي", layout="centered")
st.sidebar.title("نظام الحضور الذكي 🛡️")
choice = st.sidebar.radio("القائمة:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- أولاً: صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ تسجيل موظف جديد")
    
    # جلب الموقع مسبقاً لضمان وجوده
    current_loc = get_geolocation()
    
    with st.form("admin_reg_form", clear_on_submit=True):
        name = st.text_input("الاسم الكامل")
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        uploaded_image = st.camera_input("التقط الصورة المرجعية")
        
        st.warning("سيتم تحديد موقعك الحالي كمقر عمل إلزامي.")
        
        if current_loc:
            st.success("📍 تم تحديد موقعك الجغرافي.")
        else:
            st.info("📡 جاري البحث عن موقعك...")
            
        submitted = st.form_submit_button("حفظ الموظف")
        
    if submitted:
        if name and email and uploaded_image and current_loc:
            try:
                with st.spinner("جاري الحفظ..."):
                    email_clean = email.strip().lower()
                    file_path = f"{email_clean}.jpg"
                    
                    # 1. رفع الصورة (إدارة الخطأ بشكل منفصل)
                    try:
                        supabase.storage.from_("employee_faces").upload(
                            path=file_path,
                            file=uploaded_image.getvalue(),
                            file_options={"content-type": "image/jpeg", "upsert": "true"}
                        )
                    except:
                        pass # إذا كانت الصورة موجودة مسبقاً
                        
                    img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                    
                    # 2. حفظ البيانات في جدول الموظفين
                    emp_data = {
                        "full_name": name,
                        "email": email_clean,
                        "password": password,
                        "profile_pic_url": img_url,
                        "work_lat": current_loc['coords']['latitude'],
                        "work_lon": current_loc['coords']['longitude']
                    }
                    supabase.table("employees").insert(emp_data).execute()
                    st.success(f"✅ تم تسجيل الموظف {name} بنجاح!")
            except Exception as e:
                st.error(f"❌ خطأ: {e}")
        else:
            st.error("⚠️ يرجى إكمال الحقول والتأكد من تفعيل الموقع.")

# ----------------- ثانياً: صفحة الموظف (User) -----------------
else:
    st.header("📱 بوابة تسجيل الحضور")
    user_loc = get_geolocation()
    
    with st.form("user_login"):
        email_in = st.text_input("أدخل بريدك الإلكتروني")
        login_btn = st.form_submit_button("بدء التحقق")
    
    if login_btn and email_in:
        res = supabase.table("employees").select("*").eq("email", email_in.strip().lower()).execute()
        if res.data:
            user = res.data[0]
            st.success(f"مرحباً {user['full_name']}")
            live_img = st.camera_input("صور وجهك للتحقق")
            
            if live_img and user_loc:
                dist = check_location(user_loc['coords']['latitude'], user_loc['coords']['longitude'], user['work_lat'], user['work_lon'])
                
                if dist <= 100:
                    with st.spinner("جاري مطابقة الوجه..."):
                        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tfile.write(live_img.read())
                        try:
                            result = DeepFace.verify(tfile.name, user['profile_pic_url'], enforce_detection=False)
                            if result['verified']:
                                st.success("✅ تم التحقق بنجاح!")
                                try:
                                    supabase.table("attendance_logs").insert({"employee_id": user['id'], "status": "Check-in"}).execute()
                                    st.balloons()
                                except:
                                    st.info("تم التحقق، ولكن واجهنا مشكلة في تسجيل اللوج (تأكد من تعطيل RLS لجدول attendance_logs).")
                            else:
                                st.error("❌ الوجه غير مطابق.")
                        finally:
                            os.remove(tfile.name)
                else:
                    st.error(f"📍 أنت بعيد عن العمل بمسافة {int(dist)} متر.")
        else:
            st.error("❌ البريد غير مسجل.")
