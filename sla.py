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
    .main {
        background-color: #f8fafc;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #4A90E2 0%, #8B5CF6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.6rem;
        font-weight: 600;
    }
    .stButton>button:hover {
        opacity: 0.9;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
    }
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

available_request_types = [
    "Ask a question",
    "Emailed request",
    "CC Talep veya olay gönderin",
    "None"
]

request_type_filter = st.sidebar.multiselect(
    "Kayıt Türü", 
    available_request_types, 
    default=available_request_types
)

date_filter_type = st.sidebar.radio(
    "Tarih Filtre Türü",
    ["Oluşturulma Tarihi", "Kapanış Tarihi", "Tarih Filtresi Yok"]
)

col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Başlangıç", value=date.today().replace(day=1))
with col2:
    end_date = st.date_input("Bitiş", value=date.today())

max_results = st.sidebar.number_input("Maksimum Kayıt", value=200, min_value=10, max_value=1000, step=50)

st.sidebar.divider()

# Filtreler
st.sidebar.subheader("🎯 Filtreler")

available_statuses = [
    "To Do",
    "In Progress",
    "Done",
    "Waiting for support",
    "Waiting for customer"
]

available_sla_states = ["🕓 Açık", "✅ Zamanında", "❌ Havuzda Bekliyor", "⚠️ Eskalasyon", "❌ SLA Dışı"]
available_assignees = ["Unassigned", "Murat Çali", "Ceren Gülsoy", "Onur Delibaşı"]

status_filter = st.sidebar.multiselect("Statü", available_statuses, default=available_statuses)
sla_filter = st.sidebar.multiselect("SLA Durumu", available_sla_states, default=available_sla_states)
assignee_filter = st.sidebar.multiselect("Atanan Kişi", available_assignees, default=available_assignees)

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
    if not jira_token:
        st.error("⚠️ Lütfen API Token giriniz!")
        st.stop()
    
    if not request_type_filter:
        st.error("⚠️ En az bir Kayıt Türü seçmelisiniz!")
        st.stop()
        
    with st.spinner("🔄 Veriler getiriliyor..."):
        url = f"https://{jira_domain}/rest/api/3/search/jql"
        headers = {"Accept": "application/json"}

        # JQL sorgusu
        jql_parts = []
        for req_type in request_type_filter:
            if req_type == "None":
                jql_parts.append('"Request Type" is EMPTY')
            else:
                jql_parts.append(f'"Request Type" = "{req_type}"')
        
        request_type_condition = " OR ".join(jql_parts)
        
        # Tarih filtresi
        if date_filter_type == "Oluşturulma Tarihi":
            date_condition = f'created >= "{start_date}" AND created <= "{end_date}"'
        elif date_filter_type == "Kapanış Tarihi":
            date_condition = f'resolved >= "{start_date}" AND resolved <= "{end_date}"'
        else:
            date_condition = ""
        
        if date_condition:
            jql = f'project = "{project_key}" AND ({request_type_condition}) AND {date_condition} ORDER BY created DESC'
        else:
            jql = f'project = "{project_key}" AND ({request_type_condition}) ORDER BY created DESC'

        # Pagination
        all_issues = []
        start_at = 0
        max_per_request = 100
        total_to_fetch = int(max_results)
        total_available = None
        
        try:
            while len(all_issues) < total_to_fetch:
                remaining = total_to_fetch - len(all_issues)
                current_max = min(max_per_request, remaining)
                
                params = {
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": current_max,
                    "fields": "summary,created,assignee,status,issuetype",
                    "expand": "changelog"
                }

                auth = HTTPBasicAuth(jira_email, jira_token)
                res = requests.get(url, headers=headers, params=params, auth=auth, timeout=30)
                
                if res.status_code != 200:
                    st.error(f"❌ API Hatası: {res.status_code}")
                    st.error(f"Detay: {res.text}")
                    with st.expander("🔍 JQL Sorgusu"):
                        st.code(jql)
                    st.stop()

                data = res.json()
                issues = data.get("issues", [])
                
                if total_available is None:
                    total_available = data.get("total", 0)
                
                if not issues:
                    break
                
                all_issues.extend(issues)
                
                progress_msg = f"📥 {len(all_issues)}"
                if total_available > 0:
                    progress_msg += f" / {min(total_to_fetch, total_available)}"
                st.sidebar.info(progress_msg)
                
                if len(issues) < current_max:
                    break
                
                if total_available and len(all_issues) >= total_available:
                    break
                
                start_at += len(issues)
            
            if not all_issues:
                st.warning("⚠️ Hiç kayıt bulunamadı.")
                st.stop()
            
            st.sidebar.success(f"✅ {len(all_issues)} kayıt getirildi!")
            
            # Debug bilgisi
            with st.expander("🔍 Debug Bilgisi"):
                st.write(f"**JQL:** {jql}")
                st.write(f"**API Toplam:** {total_available}")
                st.write(f"**Getirilen:** {len(all_issues)}")
            
            results = []

            for issue in all_issues:
                key = issue["key"]
                fields = issue.get("fields", {})
                summary = fields.get("summary", "")
                status_name = fields.get("status", {}).get("name", "")
                issue_type = fields.get("issuetype", {}).get("name", "")
                created_str = fields.get("created")
                created_dt = parse_dt(created_str)

                changelog = issue.get("changelog", {}).get("histories", [])
                assigned_dt = None
                done_dt = None
                assignee_name = fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None

                for entry in sorted(changelog, key=lambda x: x["created"]):
                    for item in entry.get("items", []):
                        if item.get("field") == "assignee" and not assigned_dt:
                            to_val = item.get("to")
                            if to_val:
                                assigned_dt = parse_dt(entry["created"])
                        elif item.get("field") == "status":
                            to_string = item.get("toString", "")
                            if to_string == "Done" and not done_dt:
                                done_dt = parse_dt(entry["created"])
                            elif to_string in ["Closed", "Resolved", "Completed"] and not done_dt:
                                done_dt = parse_dt(entry["created"])

                if not assignee_name:
                    assignee_name = "Unassigned"

                havuz_suresi = round((assigned_dt - created_dt).total_seconds() / 3600, 2) if assigned_dt else None
                yanit_suresi = round((done_dt - assigned_dt).total_seconds() / 3600, 2) if assigned_dt and done_dt else None
                toplam_sure = round((done_dt - created_dt).total_seconds() / 3600, 2) if done_dt else None

                if not assigned_dt:
                    sla = "❌ Havuzda Bekliyor"
                elif not done_dt:
                    sla = "🕓 Açık"
                else:
                    if yanit_suresi <= 72:
                        sla = "✅ Zamanında"
                    elif yanit_suresi <= 84:
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
                    "SLA Durumu": sla
                })

            df = pd.DataFrame(results)

            # Filtreler
            df = df[df["Statü"].isin(status_filter)]
            df = df[df["SLA Durumu"].isin(sla_filter)]
            df = df[df["Atanan Kişi"].isin(assignee_filter)]
            
            # Benzersiz değerler
            with st.expander("📋 Verideki Benzersiz Değerler"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write("**Statüler:**")
                    st.write(sorted(pd.DataFrame(results)["Statü"].unique().tolist()))
                with col2:
                    st.write("**SLA Durumları:**")
                    st.write(sorted(pd.DataFrame(results)["SLA Durumu"].unique().tolist()))
                with col3:
                    st.write("**Atanan Kişiler:**")
                    st.write(sorted(pd.DataFrame(results)["Atanan Kişi"].unique().tolist()))

            if df.empty:
                st.warning("⚠️ Filtreler uygulandıktan sonra hiç sonuç kalmadı.")
            else:
                st.success(f"✅ {len(df)} kayıt bulundu")
                
                # Özet metrikler
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("📊 Toplam Kayıt", len(df))
                
                with col2:
                    done_count = len(df[df["Statü"].isin(["Done", "Closed", "Resolved", "Completed"])])
                    st.metric("✅ Kapanan", done_count)
                
                with col3:
                    open_count = len(df[~df["Statü"].isin(["Done", "Closed", "Resolved", "Completed"])])
                    st.metric("📝 Açık", open_count)
                
                with col4:
                    avg_response = df["Yanıtlama Süresi (saat)"].mean()
                    avg_str = f"{avg_response:.1f}" if not pd.isna(avg_response) else "N/A"
                    st.metric("⏱️ Ort. Yanıt (saat)", avg_str)
                
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
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # SLA Dağılımı
                        st.subheader("SLA Durumu Dağılımı")
                        sla_counts = df["SLA Durumu"].value_counts()
                        fig1 = px.pie(
                            values=sla_counts.values,
                            names=sla_counts.index,
                            hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Set3
                        )
                        fig1.update_layout(height=400)
                        st.plotly_chart(fig1, use_container_width=True)
                    
                    with col2:
                        # Statü Dağılımı
                        st.subheader("Statü Dağılımı")
                        status_counts = df["Statü"].value_counts()
                        fig2 = px.bar(
                            x=status_counts.index,
                            y=status_counts.values,
                            labels={'x': 'Statü', 'y': 'Kayıt Sayısı'},
                            color=status_counts.values,
                            color_continuous_scale='Blues'
                        )
                        fig2.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    # Atanan kişi dağılımı
                    st.subheader("Atanan Kişi Dağılımı")
                    assignee_counts = df["Atanan Kişi"].value_counts()
                    fig3 = px.bar(
                        x=assignee_counts.index,
                        y=assignee_counts.values,
                        labels={'x': 'Atanan Kişi', 'y': 'Kayıt Sayısı'},
                        color=assignee_counts.values,
                        color_continuous_scale='Purples'
                    )
                    fig3.update_layout(height=350, showlegend=False)
                    st.plotly_chart(fig3, use_container_width=True)
                
                with tab3:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Yanıtlama Süreleri")
                        response_times = df["Yanıtlama Süresi (saat)"].dropna()
                        if not response_times.empty:
                            st.metric("Ortalama", f"{response_times.mean():.1f} saat")
                            st.metric("Minimum", f"{response_times.min():.1f} saat")
                            st.metric("Maksimum", f"{response_times.max():.1f} saat")
                            st.metric("Medyan", f"{response_times.median():.1f} saat")
                        else:
                            st.info("Yanıt süresi verisi yok")
                    
                    with col2:
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
            
else:
    # Karşılama ekranı
    st.info("👈 Soldaki menüden ayarları yapıp **'Verileri Getir'** butonuna tıklayın")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 📊 Detaylı Raporlar")
        st.write("Jira kayıtlarınızı detaylı şekilde analiz edin")
    with col2:
        st.markdown("### ⏱️ SLA Takibi")
        st.write("SLA sürelerinizi takip edin ve raporlayın")
    with col3:
        st.markdown("### 📈 Performans Analizi")
        st.write("Ekip performansını görselleştirin")