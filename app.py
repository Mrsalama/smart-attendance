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

# دالة حساب المسافة الجغرافية
def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

# --- إعداد واجهة التطبيق ---
st.set_page_config(page_title="نظام الحضور الذكي", layout="centered")
st.sidebar.title("نظام الحضور الذكي 🛡️")
st.sidebar.info("مرحباً بك يا أستاذ محمد")
choice = st.sidebar.radio("انتقل إلى:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- أولاً: صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ لوحة تحكم المسؤول")
    
    # طلب الموقع في بداية الصفحة ليكون جاهزاً ومتاحاً عند الضغط على الزر
    current_loc = get_geolocation()
    
    with st.form("admin_reg_form"):
        name = st.text_input("الاسم الكامل للموظف")
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        uploaded_image = st.camera_input("التقط الصورة المرجعية لوجه الموظف")
        
        st.warning("سيتم تحديد موقعك الحالي كمقر عمل إلزامي لهذا الموظف.")
        
        # عرض حالة الموقع للمسؤول لضمان نجاح الجلب
        if current_loc:
            st.success("📍 تم تحديد موقعك الجغرافي بنجاح.")
        else:
            st.info("📡 جاري البحث عن موقعك... يرجى الانتظار ثانية حتى تظهر العلامة الخضراء.")
            
        submitted_admin = st.form_submit_button("حفظ بيانات الموظف")
        
    if submitted_admin:
        if name and email and uploaded_image and current_loc:
            try:
                with st.spinner("جاري حفظ البيانات ورفع الصورة..."):
                    # 1. رفع الصورة لـ Storage
                    email_clean = email.strip().lower()
                    file_path = f"faces/{email_clean}.jpg"
                    supabase.storage.from_("employee_faces").upload(
                        path=file_path,
                        file=uploaded_image.getvalue(),
                        file_options={"content-type": "image/jpeg"}
                    )
                    img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                    
                    # 2. حفظ البيانات في جدول Employees
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
                st.error(f"❌ حدث خطأ أثناء الحفظ: {e}")
        else:
            st.error("⚠️ يرجى إكمال جميع الحقول والتأكد من ظهور علامة الموقع الخضراء.")

# ----------------- ثانياً: صفحة الموظف (User) -----------------
else:
    st.header("📱 بوابة تسجيل الحضور")
    
    # جلب الموقع مسبقاً أيضاً في صفحة الموظف
    user_current_loc = get_geolocation()
    
    with st.form("user_login_form"):
        email_input = st.text_input("أدخل بريدك الإلكتروني المسجل")
        search_button = st.form_submit_button("بدء عملية التحقق")
    
    if search_button and email_input:
        with st.spinner("جاري البحث عن بياناتك..."):
            res = supabase.table("employees").select("*").eq("email", email_input.strip().lower()).execute()
            
        if res.data:
            user = res.data[0]
            st.success(f"أهلاً {user['full_name']}! يرجى إكمال التحقق أدناه:")
            
            # التقاط الصورة الحية
            live_img = st.camera_input("التقط صورة لوجهك الآن")
            
            if live_img and user_current_loc:
                # 1. التحقق من الموقع الجغرافي (Geofencing)
                dist = check_location(
                    user_current_loc['coords']['latitude'], 
                    user_current_loc['coords']['longitude'], 
                    user['work_lat'], 
                    user['work_lon']
                )
                
                if dist <= 100: # النطاق المسموح 100 متر
                    st.info("📍 الموقع الجغرافي صحيح.")
                    
                    with st.spinner("جاري مطابقة الوجه بالذكاء الاصطناعي..."):
                        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tfile.write(live_img.read())
                        
                        try:
                            # مقارنة الصور باستخدام DeepFace
                            result = DeepFace.verify(
                                img1_path = tfile.name,
                                img2_path = user['profile_pic_url'],
                                enforce_detection = False
                            )
                            
                            if result['verified']:
                                st.success("✅ تم التحقق من الهوية بنجاح!")
                                # تسجيل الحضور في جدول Logs
                                log_data = {"employee_id": user['id'], "status": "Check-in"}
                                supabase.table("attendance_logs").insert(log_data).execute()
                                st.balloons()
                            else:
                                st.error("❌ عذراً، لم يتطابق الوجه. حاول مرة أخرى.")
                        except Exception as e:
                            st.error(f"⚠️ خطأ في تحليل الصورة: {e}")
                        finally:
                            os.remove(tfile.name)
                else:
                    st.error(f"📍 موقعك غير صحيح! أنت بعيد عن العمل بمسافة {int(dist)} متر.")
            elif not user_current_loc:
                st.warning("📡 يرجى السماح بالوصول للموقع والانتظار ثانية لتحديده.")
        else:
            st.error("❌ هذا البريد الإلكتروني غير مسجل.")
