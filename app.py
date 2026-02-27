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
    st.error("⚠️ خطأ في قراءة المفاتيح من Secrets. تأكد من إضافتها في إعدادات Streamlit Cloud.")
    st.stop()

# دالة حساب المسافة
def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

# --- واجهة التطبيق ---
st.sidebar.title("نظام الحضور الذكي 🛡️")
st.sidebar.info("مرحباً بك يا أستاذ محمد")
choice = st.sidebar.radio("انتقل إلى:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- أولاً: صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ لوحة تحكم المسؤول")
    
    with st.form("admin_reg_form"):
        name = st.text_input("الاسم الكامل للموظف")
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        uploaded_image = st.camera_input("التقط الصورة المرجعية")
        
        st.warning("سيتم تحديد موقعك الحالي كمقر عمل لهذا الموظف.")
        submitted_admin = st.form_submit_button("حفظ بيانات الموظف")
        
    if submitted_admin:
        # استدعاء الموقع الجغرافي داخل كتلة الشرط مع إزاحة صحيحة
        loc = get_geolocation()
        
        if name and email and uploaded_image and loc:
            try:
                with st.spinner("جاري حفظ البيانات..."):
                    # رفع الصورة
                    file_path = f"faces/{email.strip().lower()}.jpg"
                    supabase.storage.from_("employee_faces").upload(
                        path=file_path,
                        file=uploaded_image.getvalue(),
                        file_options={"content-type": "image/jpeg"}
                    )
                    img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                    
                    # حفظ في القاعدة
                    emp_data = {
                        "full_name": name,
                        "email": email.strip().lower(),
                        "password": password,
                        "profile_pic_url": img_url,
                        "work_lat": loc['coords']['latitude'],
                        "work_lon": loc['coords']['longitude']
                    }
                    supabase.table("employees").insert(emp_data).execute()
                    st.success(f"✅ تم تسجيل الموظف {name} بنجاح!")
            except Exception as e:
                st.error(f"❌ حدث خطأ: {e}")
        else:
            st.error("⚠️ يرجى التأكد من ملء الحقول والسماح بالوصول للموقع والكاميرا.")

# ----------------- ثانياً: صفحة الموظف (User) -----------------
else:
    st.header("📱 بوابة تسجيل الحضور")
    
    with st.form("user_login_form"):
        email_input = st.text_input("أدخل بريدك الإلكتروني")
        search_button = st.form_submit_button("بدء التحقق")
    
    if search_button and email_input:
        res = supabase.table("employees").select("*").eq("email", email_input.strip().lower()).execute()
            
        if res.data:
            user = res.data[0]
            st.success(f"أهلاً {user['full_name']}")
            
            live_img = st.camera_input("التقط صورة لوجهك")
            user_loc = get_geolocation()
            
            if live_img and user_loc:
                dist = check_location(
                    user_loc['coords']['latitude'], 
                    user_loc['coords']['longitude'], 
                    user['work_lat'], 
                    user['work_lon']
                )
                
                if dist <= 100:
                    with st.spinner("جاري مطابقة الوجه..."):
                        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tfile.write(live_img.read())
                        try:
                            result = DeepFace.verify(
                                img1_path = tfile.name,
                                img2_path = user['profile_pic_url'],
                                enforce_detection = False
                            )
                            if result['verified']:
                                st.success("✅ تم التحقق بنجاح!")
                                log_data = {"employee_id": user['id'], "status": "Check-in"}
                                supabase.table("attendance_logs").insert(log_data).execute()
                                st.balloons()
                            else:
                                st.error("❌ الوجه غير مطابق.")
                        finally:
                            os.remove(tfile.name)
                else:
                    st.error(f"📍 موقعك غير صحيح! المسافة: {int(dist)} متر.")
        else:
            st.error("❌ البريد غير مسجل.")
