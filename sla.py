import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go

# Sayfa yapılandırması
st.set_page_config(
    page_title="Ozan - Jira SLA Raporu",
    page_icon="🔵",
    layout="wide"
)

# Custom CSS - Daha minimal
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #4A90E2 0%, #8B5CF6 100%);
        color: white; border: none; border-radius: 8px;
        padding: 0.6rem; font-weight: 600;
    }
    .stButton>button:hover { opacity: 0.9; }
    div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

# Header
st.title("🔵 Ozan - Jira SLA Rapor Arayüzü")
st.markdown("Müşteri Hizmetleri Performans İzleme Paneli")
st.divider()

# Sidebar
st.sidebar.title("⚙️ Ayarlar")

# Bağlantı Ayarları
st.sidebar.subheader("🔗 Jira Bağlantısı")
jira_domain = st.sidebar.text_input("Jira Domain", value="ozan.atlassian.net")
jira_email = st.sidebar.text_input("Jira Email", value="")
jira_token = st.sidebar.text_input("API Token", type="password")
project_key = st.sidebar.text_input("Proje Kodu", value="CC")

st.sidebar.divider()

# Sorgu Parametreleri
st.sidebar.subheader("📋 Sorgu Parametreleri")

# Request Type Filtresi - OPSİYONEL
use_request_type = st.sidebar.checkbox("Request Type Filtresi Kullan", value=False)

if use_request_type:
    available_request_types = [
        "Ask a question",
        "Emailed request",
        "CC Talep veya olay gönderin",
        "None"
    ]
    request_type_filter = st.sidebar.multiselect("Kayıt Türü", available_request_types, default=[])
else:
    request_type_filter = []

date_filter_type = st.sidebar.radio(
    "Tarih Filtre Türü",
    ["Oluşturulma Tarihi", "Kapanış Tarihi", "Tarih Filtresi Yok"]
)

col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Başlangıç", value=date.today().replace(day=1))
with col2:
    end_date = st.date_input("Bitiş", value=date.today())

max_results = st.sidebar.number_input("Maksimum Kayıt", value=200, min_value=10, max_value=5000, step=50)

st.sidebar.divider()

# Filtreler
st.sidebar.subheader("🎯 Filtreler")
available_statuses = ["To Do", "In Progress", "Done", "Waiting for support", "Waiting for customer","Open"]
available_sla_states = ["🕓 Açık", "✅ Zamanında", "❌ Havuzda Bekliyor", "⚠️ Eskalasyon", "❌ SLA Dışı"]
available_assignees = ["Unassigned", "murat.cali", "Ceren Gülsoy", "Onur Delibaşı", "Enes Yakışık","Call Center","Call Center Agent"]

status_filter = st.sidebar.multiselect("Statü", available_statuses, default=available_statuses)
sla_filter = st.sidebar.multiselect("SLA Durumu", available_sla_states, default=available_sla_states)
assignee_filter = st.sidebar.multiselect("Atanan Kişi", available_assignees, default=[])

st.sidebar.divider()
fetch_button = st.sidebar.button("🔄 Verileri Getir")

def parse_dt(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

if fetch_button:
    if not jira_token or not jira_email:
        st.error("⚠️ Lütfen Jira Email ve API Token giriniz!")
        st.stop()

    with st.spinner("🔄 Veriler getiriliyor..."):
        # ✅ Yeni, kalıcı endpoint
        url_search = f"https://{jira_domain}/rest/api/3/search/jql"
        url_count  = f"https://{jira_domain}/rest/api/3/search/approximate-count"
        headers = {
            "Accept": "application/json",
        }
        auth = HTTPBasicAuth(jira_email, jira_token)

        try:
            # JQL oluştur
            jql_parts = [f'project = "{project_key}"']

            if use_request_type and request_type_filter:
                rt_conditions = []
                for req_type in request_type_filter:
                    if req_type == "None":
                        rt_conditions.append('"Request Type" is EMPTY')
                    else:
                        rt_conditions.append(f'"Request Type" = "{req_type}"')
                if rt_conditions:
                    jql_parts.append("(" + " OR ".join(rt_conditions) + ")")

            if date_filter_type == "Oluşturulma Tarihi":
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                jql_parts.append(f'created >= "{start_str}" AND created <= "{end_str} 23:59"')
            elif date_filter_type == "Kapanış Tarihi":
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                jql_parts.append(f'resolved >= "{start_str}" AND resolved <= "{end_str} 23:59"')

            jql = " AND ".join(jql_parts) + " ORDER BY created DESC"

            # (Opsiyonel) Yaklaşık toplam
            approx_total = None
            try:
                res_cnt = requests.post(
                    url_count,
                    headers={**headers, "Content-Type": "application/json"},
                    json={"jql": jql},
                    auth=auth,
                    timeout=30
                )
                if res_cnt.status_code == 200:
                    approx_total = res_cnt.json().get("count")
            except requests.exceptions.RequestException:
                pass

            # 🔁 Yeni sayfalama: nextPageToken
            all_issues = []
            next_token = None
            max_per_request = 100
            total_to_fetch = int(max_results)
            iteration_count = 0

            while len(all_issues) < total_to_fetch and iteration_count < 200:
                iteration_count += 1
                remaining = total_to_fetch - len(all_issues)
                current_max = min(max_per_request, remaining)

                params = {
                    "jql": jql,
                    "maxResults": current_max,
                    "fields": ["summary", "created", "assignee", "status", "issuetype", "resolutiondate","labels"],
                    "expand": "changelog"
                }
                if next_token:
                    params["nextPageToken"] = next_token

                res = requests.get(url_search, headers=headers, params=params, auth=auth, timeout=30)

                if res.status_code == 410:
                    st.error("❌ Jira, eski arama endpoint'lerini kaldırdı.")
                    st.info("ℹ️ `/rest/api/3/search/jql` kullanılıyor olmalı ve sayfalama `nextPageToken` ile yapılmalı (bu sürüm bunu zaten yapıyor).")
                    st.stop()

                if res.status_code != 200:
                    st.error(f"❌ API Hatası: {res.status_code}")
                    st.error(f"Detay: {res.text}")
                    st.stop()

                data = res.json()
                issues = data.get("issues", [])
                all_issues.extend(issues)

                next_token = data.get("nextPageToken")
                is_last = data.get("isLast", True)

                if is_last or not issues or not next_token:
                    break

            if not all_issues:
                st.warning("⚠️ Hiç kayıt bulunamadı.")
                st.stop()

            # Verileri işle
            results = []
            for issue in all_issues:
                key = issue["key"]
                fields = issue.get("fields", {})
                summary = fields.get("summary", "")
                status_name = fields.get("status", {}).get("name", "")
                issue_type = fields.get("issuetype", {}).get("name", "")
                created_str = fields.get("created")
                created_dt = parse_dt(created_str)
                resolution_date_str = fields.get("resolutiondate")
                labels = fields.get("labels", [])
                labels_str = ", ".join(labels) if labels else ""

                changelog = issue.get("changelog", {}).get("histories", [])
                assigned_dt = None
                done_dt = None
                assignee_name = fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None

                # Changelog'dan atama ve kapanma
                for entry in sorted(changelog, key=lambda x: x["created"]):
                    for item in entry.get("items", []):
                        if item.get("field") == "assignee" and not assigned_dt:
                            if item.get("to"):
                                assigned_dt = parse_dt(entry["created"])
                        elif item.get("field") == "status":
                            if item.get("toString", "") in ["Done", "Closed", "Resolved", "Completed"] and not done_dt:
                                done_dt = parse_dt(entry["created"])

                if not done_dt and status_name in ["Done", "Closed", "Resolved", "Completed"]:
                    if resolution_date_str:
                        done_dt = parse_dt(resolution_date_str)

                if not assignee_name:
                    assignee_name = "Unassigned"

                # Bazı kayıtlar oluşturulurken doğrudan atanmış olabilir.
                # Bu durumda değişiklik kaydı oluşmadığından assigned_dt boş kalır ve
                # kayıt hatalı biçimde "Havuzda Bekliyor" olarak işaretlenir.
                if assigned_dt is None and assignee_name != "Unassigned" and created_dt is not None:
                    assigned_dt = created_dt

                # ✅ ARKA PLANDA FİLTRELEME - Eğer atanan kişi filtresi varsa ve bu kayıt seçili değilse atla
                if assignee_filter and assignee_name not in assignee_filter:
                    continue

                # Süreler (saat)
                havuz_suresi = yanit_suresi = toplam_sure = None
                if created_dt and assigned_dt:
                    havuz_suresi = round((assigned_dt - created_dt).total_seconds() / 3600, 2)
                if assigned_dt and done_dt:
                    yanit_suresi = round((done_dt - assigned_dt).total_seconds() / 3600, 2)
                if created_dt and done_dt:
                    toplam_sure = round((done_dt - created_dt).total_seconds() / 3600, 2)

                # SLA durumu
                if not assigned_dt:
                    sla = "❌ Havuzda Bekliyor"
                elif not done_dt:
                    sla = "🕓 Açık"
                else:
                    if yanit_suresi is not None and yanit_suresi <= 72:
                        sla = "✅ Zamanında"
                    elif yanit_suresi is not None and yanit_suresi <= 84:
                        sla = "⚠️ Eskalasyon"
                    else:
                        sla = "❌ SLA Dışı"

                results.append({
                    "Issue Key": key,
                    "Summary": summary,
                    "Oluşturulma": created_dt,
                    "Atama Zamanı": assigned_dt,
                    "Kapanış Zamanı": done_dt,
                    "Atanan Kişi": assignee_name,
                    "Statü": status_name,
                    "Kayıt Türü": issue_type,
                    "Havuz Süresi (saat)": havuz_suresi,
                    "Yanıtlama Süresi (saat)": yanit_suresi,
                    "Toplam Süre (saat)": toplam_sure,
                    "Label": labels_str,
                    "SLA Durumu": sla
                })

            # ✅ Eğer atanan kişi filtresi sonucunda hiç kayıt kalmadıysa
            if not results:
                st.warning("⚠️ Seçtiğiniz atanan kişi filtresine uygun kayıt bulunamadı.")
                st.stop()

            df = pd.DataFrame(results)

            # Filtreler - Statü ve SLA
            original_count = len(df)
            
            if status_filter:
                df = df[df["Statü"].isin(status_filter)]
            
            if sla_filter:
                df = df[df["SLA Durumu"].isin(sla_filter)]
            
            filtered_count = len(df)
            if filtered_count < original_count:
                st.info(f"🎯 Filtreler sonrası: {filtered_count} kayıt (çıkarılan: {original_count - filtered_count})")

            if df.empty:
                st.warning("⚠️ Filtreler uygulandıktan sonra hiç sonuç kalmadı.")
            else:
                st.success(f"✅ {len(df)} kayıt bulundu")

                # Özet metrikler
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("📊 Toplam Kayıt", len(df))
                with c2:
                    done_count = len(df[df["Statü"].isin(["Done", "Closed", "Resolved", "Completed"])])
                    st.metric("✅ Kapanan", done_count)
                with c3:
                    open_count = len(df[~df["Statü"].isin(["Done", "Closed", "Resolved", "Completed"])])
                    st.metric("📝 Açık", open_count)
                with c4:
                    avg_response = df["Yanıtlama Süresi (saat)"].mean()
                    st.metric("⏱️ Ort. Yanıt (saat)", f"{avg_response:.1f}" if pd.notna(avg_response) else "N/A")

                st.divider()

                # Grafikler
                tab1, tab2, tab3 = st.tabs(["📊 Tablo", "📈 Grafikler", "📋 İstatistikler"])

                with tab1:
                    st.dataframe(df, use_container_width=True, height=500)
                    st.download_button(
                        label="📥 CSV olarak indir",
                        data=df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"jira_sla_raporu_{date.today()}.csv",
                        mime="text/csv"
                    )

                with tab2:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("SLA Durumu Dağılımı")
                        sla_counts = df["SLA Durumu"].value_counts()
                        fig1 = px.pie(values=sla_counts.values, names=sla_counts.index, hole=0.4,
                                      color_discrete_sequence=px.colors.qualitative.Set3)
                        fig1.update_layout(height=400)
                        st.plotly_chart(fig1, use_container_width=True)
                    with c2:
                        st.subheader("Statü Dağılımı")
                        status_counts = df["Statü"].value_counts()
                        fig2 = px.bar(x=status_counts.index, y=status_counts.values,
                                      labels={'x': 'Statü', 'y': 'Kayıt Sayısı'},
                                      color=status_counts.values, color_continuous_scale='Blues')
                        fig2.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig2, use_container_width=True)

                    st.subheader("Atanan Kişi Dağılımı")
                    assignee_counts = df["Atanan Kişi"].value_counts()
                    fig3 = px.bar(x=assignee_counts.index, y=assignee_counts.values,
                                  labels={'x': 'Atanan Kişi', 'y': 'Kayıt Sayısı'},
                                  color=assignee_counts.values, color_continuous_scale='Purples')
                    fig3.update_layout(height=350, showlegend=False)
                    st.plotly_chart(fig3, use_container_width=True)

                with tab3:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("Yanıtlama Süreleri")
                        response_times = df["Yanıtlama Süresi (saat)"].dropna()
                        if not response_times.empty:
                            st.metric("Ortalama", f"{response_times.mean():.1f} saat")
                            st.metric("Minimum", f"{response_times.min():.1f} saat")
                            st.metric("Maksimum", f"{response_times.max():.1f} saat")
                            st.metric("Medyan", f"{response_times.median():.1f} saat")
                        else:
                            st.info("Yanıt süresi verisi yok")
                    with c2:
                        st.subheader("Havuz Süreleri")
                        pool_times = df["Havuz Süresi (saat)"].dropna()
                        if not pool_times.empty:
                            st.metric("Ortalama", f"{pool_times.mean():.1f} saat")
                            st.metric("Minimum", f"{pool_times.min():.1f} saat")
                            st.metric("Maksimum", f"{pool_times.max():.1f} saat")
                            st.metric("Medyan", f"{pool_times.median():.1f} saat")
                        else:
                            st.info("Havuz süresi verisi yok")

        except requests.exceptions.RequestException as e:
            st.error(f"❌ Bağlantı hatası: {str(e)}")
            st.info("💡 İnternet bağlantınızı ve Jira erişim bilgilerinizi kontrol edin.")
        except Exception as e:
            st.error(f"❌ Beklenmeyen hata: {str(e)}")
            st.info("💡 Lütfen sayfayı yenileyin ve tekrar deneyin.")

else:
    # Karşılama ekranı
    st.info("👈 Soldaki menüden ayarları yapıp **'Verileri Getir'** butonuna tıklayın")
    with st.expander("📚 Kullanım Kılavuzu"):
        st.markdown("""
        ### 🔐 API Token Oluşturma
        1. Atlassian API Tokens sayfasına gidin
        2. "Create API token" butonuna tıklayın
        3. Token'a bir isim verin (örn: "SLA Raporu")
        4. Oluşturulan token'ı kopyalayın

        ### ⚙️ Ayarlar
        - **Jira Domain**: Şirketinizin Jira domain'i (örn: ozan.atlassian.net)
        - **Jira Email**: Jira hesabınızın email adresi
        - **API Token**: Oluşturduğunuz token
        - **Proje Kodu**: Analiz etmek istediğiniz proje kodu (örn: CC)

        ### 🗓️ Tarih Filtreleri
        - **Oluşturulma Tarihi**: Kayıtların oluşturulma tarihine göre filtreler
        - **Kapanış Tarihi**: Kayıtların kapanma tarihine göre filtreler
        - **Tarih Filtresi Yok**: Tüm kayıtları getirir
        """)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### 📊 Detaylı Raporlar")
        st.write("Jira kayıtlarınızı detaylı şekilde analiz edin")
    with c2:
        st.markdown("### ⏱️ SLA Takibi")
        st.write("SLA sürelerinizi takip edin ve raporlayın")
    with c3:
        st.markdown("### 📈 Performans Analizi")
        st.write("Ekip performansını görselleştirin")