import streamlit as st
from supabase import create_client, Client

# تنظيف المفاتيح من أي مسافات أو رموز مخفية قد تسبب UnicodeEncodeError
SUPABASE_URL = "https://vdklirvbgwdkyvehhlba.supabase.co".strip()
SUPABASE_KEY = "sb_publishable_Jn4gl3IEq-FbtGTA0j5fhg_xhFCtEuR".strip()

try:
    # إنشاء اتصال بقاعدة البيانات
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"فشل الاتصال بـ Supabase: {e}")

# دالة للتحقق من المسافة الجغرافية
def check_location(user_lat, user_lon, work_lat, work_lon):
    distance = geodesic((user_lat, user_lon), (work_lat, work_lon)).meters
    return distance

# --- واجهة التطبيق ---
st.sidebar.title("نظام الحضور الذكي 🛡️")
choice = st.sidebar.radio("انتقل إلى:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ تسجيل موظف جديد")
    with st.form("admin_form"):
        name = st.text_input("الاسم الكامل")
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        uploaded_image = st.camera_input("التقط الصورة المرجعية للوجه")
        
        st.info("سيتم اعتماد موقعك الحالي كمقر عمل لهذا الموظف")
        loc = get_geolocation()
        
        if st.form_submit_button("حفظ الموظف"):
            if name and email and uploaded_image and loc:
                # رفع الصورة لـ Storage
                file_path = f"faces/{email}.jpg"
                supabase.storage.from_("employee_faces").upload(file_path, uploaded_image.getvalue())
                img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                
                # حفظ البيانات في الجدول
                data = {
                    "full_name": name, "email": email, "password": password,
                    "profile_pic_url": img_url,
                    "work_lat": loc['coords']['latitude'], "work_lon": loc['coords']['longitude']
                }
                supabase.table("employees").insert(data).execute()
                st.success(f"تم تسجيل {name} بنجاح!")
            else:
                st.error("تأكد من إدخال كافة البيانات والسماح بالوصول للموقع.")

# ----------------- صفحة الموظف (User) -----------------
else:
    st.header("📱 بوابة تسجيل الحضور")
    email_login = st.text_input("أدخل بريدك الإلكتروني")
    
    if email_login:
        res = supabase.table("employees").select("*").eq("email", email_login).execute()
        if res.data:
            user = res.data[0]
            st.write(f"مرحباً {user['full_name']}")
            live_img = st.camera_input("التقط صورة للتحقق")
            user_loc = get_geolocation()
            
            if live_img and user_loc:
                # التحقق من الموقع
                dist = check_location(user_loc['coords']['latitude'], user_loc['coords']['longitude'], user['work_lat'], user['work_lon'])
                
                if dist <= 100: # مسموح بـ 100 متر
                    with st.spinner("جاري مطابقة الوجه..."):
                        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tfile.write(live_img.read())
                        try:
                            # مطابقة الوجه مع الصورة المخزنة
                            result = DeepFace.verify(tfile.name, user['profile_pic_url'], enforce_detection=False)
                            if result['verified']:
                                st.success("✅ تم التحقق بنجاح!")
                                if st.button("تأكيد الحضور"):
                                    supabase.table("attendance_logs").insert({"employee_id": user['id'], "status": "Check-in"}).execute()
                                    st.balloons()
                            else:
                                st.error("❌ الوجه غير مطابق.")
                        finally:
                            os.remove(tfile.name)
                else:
                    st.error(f"📍 أنت خارج نطاق العمل بمسافة {int(dist)} متر.")
