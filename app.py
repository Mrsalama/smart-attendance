import streamlit as st
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation  # تأكد من هذا السطر
from deepface import DeepFace
from geopy.distance import geodesic
import tempfile
import os

# جلب المفاتيح من الـ Secrets (تأكد أنك أضفتها في إعدادات Streamlit Cloud كما شرحنا)
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(URL, KEY)
except Exception as e:
    st.error("خطأ في قراءة المفاتيح من Secrets. تأكد من إضافتها في إعدادات التطبيق.")

def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

st.sidebar.title("نظام الحضور الذكي 🛡️")
choice = st.sidebar.radio("انتقل إلى:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ تسجيل موظف جديد")
    with st.form("admin_form"):
        name = st.text_input("الاسم الكامل")
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        uploaded_image = st.camera_input("التقط الصورة المرجعية")
        
        st.info("سيتم طلب الموقع عند الضغط على زر الحفظ")
        
        # إضافة زر الإرسال المفقود داخل الفورم
        submitted = st.form_submit_button("حفظ الموظف الجديد")
        
        if submitted:
            # جلب الموقع عند الضغط على الزر فقط لتجنب الـ NameError
            loc = get_geolocation()
            if name and email and uploaded_image and loc:
                try:
                    file_path = f"faces/{email}.jpg"
                    supabase.storage.from_("employee_faces").upload(file_path, uploaded_image.getvalue())
                    img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                    
                    data = {
                        "full_name": name, "email": email, "password": password,
                        "profile_pic_url": img_url,
                        "work_lat": loc['coords']['latitude'], "work_lon": loc['coords']['longitude']
                    }
                    supabase.table("employees").insert(data).execute()
                    st.success(f"تم تسجيل {name} بنجاح!")
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الحفظ: {e}")
            else:
                st.warning("تأكد من إكمال البيانات والسماح بالوصول للموقع.")

else:
    st.header("📱 بوابة تسجيل الحضور")
    email_login = st.text_input("أدخل بريدك الإلكتروني")
    
    if email_login:
        res = supabase.table("employees").select("*").eq("email", email_login).execute()
        if res.data:
            user = res.data[0]
            st.write(f"مرحباً {user['full_name']}")
            live_img = st.camera_input("التحقق بالوجه")
            
            if live_img:
                loc = get_geolocation()
                if loc:
                    dist = check_location(loc['coords']['latitude'], loc['coords']['longitude'], user['work_lat'], user['work_lon'])
                    if dist <= 100:
                        with st.spinner("جاري المطابقة..."):
                            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                            tfile.write(live_img.read())
                            try:
                                result = DeepFace.verify(tfile.name, user['profile_pic_url'], enforce_detection=False)
                                if result['verified']:
                                    st.success("✅ تم التحقق!")
                                    if st.button("تأكيد العملية"):
                                        supabase.table("attendance_logs").insert({"employee_id": user['id'], "status": "Check-in"}).execute()
                                        st.balloons()
                                else:
                                    st.error("❌ الوجه غير مطابق.")
                            finally:
                                os.remove(tfile.name)
                    else:
                        st.error(f"📍 أنت بعيد عن العمل بمسافة {int(dist)} متر.")
