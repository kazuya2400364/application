import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
import json
import re
import datetime
import requests
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# 製品リスト読み込み
list = pd.read_csv("list.csv")


# Streamlit CloudのSecretsからGeminiAPIキーを取得してモデルを初期化する関数
def get_gemini_model():
    try:
        genai.configure(api_key="AIzaSyBXhHwts5bUUawb9bjE343vFShSTJAkXaw")
        return genai.GenerativeModel('gemini-1.5-flash')
    except KeyError:
        st.error("Gemini APIキーが Streamlit Cloud の Secrets に設定されていません。")
        return None


# GeminiAPIを使用して画像から情報を抽出する関数
def extract_info_with_gemini(model, image_bytes):
    if model is None:
        return None
    prompt = """この画像から、以下の情報を抽出して、JSON形式で出力してください。
    抽出する情報:
    - 型番
    - 製造年
    - 定格能力(冷房) (単位も含む)
    - 定格能力(暖房標準) (単位も含む)
    - 定格能力(暖房低温) (単位も含む)
    - 定格消費電力(冷房) (単位も含む)
    - 定格消費電力(暖房標準) (単位も含む)
    - 定格消費電力(暖房低温) (単位も含む)

    出力例:
    {
        "型番": "...",
        "製造年": "...",
        "定格能力(冷房)": "...",
        "定格能力(暖房標準)": "...",
        "定格能力(暖房低温)": "...",
        "定格消費電力(冷房)": "...",
        "定格消費電力(暖房標準)": "...",
        "定格消費電力(暖房低温)": "..."
    }
    """
    response = model.generate_content(
        [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
    )
    response_text = response.text.strip() #前後の空白を削除

    # ```json プレフィックスと ``` サフィックスを取り除く
    response_text = re.sub(r'^```json', '', response_text) #先頭や末尾にある可能性のあるjsonを削除
    response_text = re.sub(r'```$', '', response_text).strip() #前後の空白を削除

    if not response_text:
        st.error("Gemini API からの応答が空です。")
        return None

    try:
        # Gemini の応答が JSON 形式であると期待して解析
        extracted_data = json.loads(response_text)
        return extracted_data
    except Exception as e:
        st.error(f"抽出結果の解析に失敗しました: {e}\n応答内容: {response_text}")
        return None


# 定格能力(kW)を畳数に変換する関数
def kw_size_trans(rated_cooling_capacity):
    if rated_cooling_capacity <= 2.2:
        return 6
    elif rated_cooling_capacity <= 2.5:
        return 8
    elif rated_cooling_capacity <= 2.8:
        return 10
    elif rated_cooling_capacity <= 3.6:
        return 12
    elif rated_cooling_capacity <= 4.5:
        return 14
    else:
        return 16
    

# 省エネルギー性能・定格能力(冷房)・製造後経過年数から補助金額を算出する関数
def get_points(energy_efficient, cooling_capacity , years_passed):
  if energy_efficient >= 3.0 and cooling_capacity >= 3.6 and years_passed >= 15:
    return 70000
  elif energy_efficient >= 3.0 and cooling_capacity >= 3.6 and years_passed < 15:
    return 23000
  elif energy_efficient >= 3.0 and 2.4 <= cooling_capacity < 3.6 and years_passed >= 15:
    return 60000
  elif energy_efficient >= 3.0 and 2.4 <= cooling_capacity < 3.6 and years_passed < 15:
    return 18000
  elif energy_efficient >= 3.0 and cooling_capacity < 2.4 and years_passed >= 15:
    return 50000
  elif energy_efficient >= 3.0 and cooling_capacity < 2.4 and years_passed < 15:
    return 15000
  elif 2.0 <= energy_efficient < 3.0  and cooling_capacity >= 3.6 and years_passed >= 15:
    return 40000
  elif 2.0 <= energy_efficient < 3.0 and cooling_capacity >= 3.6 and years_passed < 15:
    return 23000
  elif 2.0 <= energy_efficient < 3.0 and 2.4 <= cooling_capacity < 3.6 and years_passed >= 15:
    return 30000
  elif 2.0 <= energy_efficient < 3.0 and 2.4 <= cooling_capacity < 3.6 and years_passed < 15:
    return 10000
  elif 2.0 <= energy_efficient < 3.0 and cooling_capacity < 2.4 and years_passed >= 15:
    return 20000
  elif 2.0 <= energy_efficient < 3.0 and cooling_capacity < 2.4 and years_passed < 15:
    return 9000
  else:
    return("対象外")


# 郵便番号から住所を取得する関数
def get_address(zip_code):
  res = requests.get("https://zipcloud.ibsnet.co.jp/api/search",
                   params={"zipcode":str(zip_code)})
  data = res.json()["results"][0]
  address = data["address1"] + data["address2"] + data["address3"]
  return address


# 以下streamlitの出力
def main():
    st.title("エアコン補助金・見積判定")

    # Gemini モデルをセッションステートに保存 (初回のみロード)
    if "gemini_model" not in st.session_state:
        st.session_state["gemini_model"] = get_gemini_model()

    uploaded_file = st.file_uploader("エアコン本体の型番が写った画像をアップロードしてください。", type=["jpg", "jpeg", "png"])
    if uploaded_file is None:
        st.write("参考例")
        st.image("photo.jpg")

    if uploaded_file is not None:
        if st.session_state.get("gemini_model"):
            image = Image.open(uploaded_file)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG')
            image_bytes = buffer.getvalue()

            st.subheader("●アップロード画像")
            st.image(image, use_container_width=True)

            extracted_info = extract_info_with_gemini(st.session_state["gemini_model"], image_bytes)

            if extracted_info:
                # DataFrame の形式を調整
                df_data = {
                    "型番": [extracted_info.get("型番")],
                    "製造年": [extracted_info.get("製造年")],
                    "定格能力(冷房)": [extracted_info.get("定格能力(冷房)")],
                    "定格能力(暖房標準)": [extracted_info.get("定格能力(暖房標準)")],
                    "定格能力(暖房低温)": [extracted_info.get("定格能力(暖房低温)")],
                    "定格消費電力(冷房)": [extracted_info.get("定格消費電力(冷房)")],
                    "定格消費電力(暖房標準)": [extracted_info.get("定格消費電力(暖房標準)")],
                    "定格消費電力(暖房低温)": [extracted_info.get("定格消費電力(暖房低温)")]
                }
                df = pd.DataFrame(df_data)
                st.markdown("&nbsp;&nbsp;&nbsp;")
                st.subheader("●エアコン情報")
                st.dataframe(df)                

                # 定格能力(冷房)を数値に変換
                rated_cooling_capacity = extracted_info.get("定格能力(冷房)")
                rated_cooling_capacity = float(re.match(r'[^+\-\d]*([+-]?\d+([.,]\d+)?).*', rated_cooling_capacity)[1])

                # 製造年を数値に変換し、製造後経過年数を算出
                manufacture_year = extracted_info.get("製造年")
                manufacture_year = int(re.match(r'[^+\-\d]*([+-]?\d+([.,]\d+)?).*', manufacture_year)[1])
                current_year = datetime.date.today().year
                years_passed = current_year - manufacture_year

                if years_passed >= 15:
                    st.info(f"### **お客様のエアコンは製造から{years_passed}年経過しているため、買い替えで20,000~70,000ポイント付与されます。**")
                    st.write(f"買い替えの場合、上記補助金が受領できるのは<span style='color:red; font-weight:bold;'>2027年3月31日</span>までです。<br>※予算の消化状況により期日が早まる可能性があります。", unsafe_allow_html=True)
                    st.markdown("&nbsp;&nbsp;&nbsp;")
                else:
                    st.info(f"### **お客様のエアコンは製造から{years_passed}年経過しているため、買い替えで9,000~23,000ポイント付与されます。**")
                    st.write(f"買い替えの場合、上記補助金が受領できるのは<span style='color:red; font-weight:bold;'>2027年3月31日</span>までです。<br>※予算の消化状況により期日が早まる可能性があります。", unsafe_allow_html=True)
                    st.markdown("&nbsp;&nbsp;&nbsp;")
                

                if st.button("詳細な見積もりはこちら"):
                    st.session_state["flage"] = True
                if "flage" in st.session_state and st.session_state["flage"]:
                    st.markdown("&nbsp;&nbsp;&nbsp;")
                    st.subheader("●製品選択")
                    st.info(f"現在ご使用中のエアコンは{kw_size_trans(rated_cooling_capacity)}畳用です。")
                    st.image("model.png")
                    _model = st.radio("",("S224ATES-W(6畳用)", "S254ATES-W(8畳用)", "S284ATES-W(10畳用)"))
                    model = _model.split("(")[0]

                    price = list[list["型番"] == model]["機器販売価格"].iloc[0]
                    cost = list[list["型番"] == model]["基本工事費"].iloc[0]
                    energy_efficient = list[list["型番"] == model]["多段階評価点"].iloc[0]
                    cooling_capacit = list[list["型番"] == model]["定格能力"].iloc[0]
                    subsidy = get_points(energy_efficient,  cooling_capacit, years_passed)

                    st.markdown("&nbsp;&nbsp;&nbsp;")
                    st.subheader("●お客さま情報")
                    st.info("myTOKYOGASアカウントをお持ちの方は、お客さま情報を自動入力できます。")
                    with open("config.yaml", encoding="utf-8") as file:
                        config = yaml.load(file, Loader=SafeLoader)

                    # Pre-hashing all plain text passwords once
                    # stauth.Hasher.hash_passwords(config['credentials'])

                    authenticator = stauth.Authenticate(
                        config["credentials"],
                        config["cookie"]["name"],
                        config["cookie"]["key"],
                        config["cookie"]["expiry_days"]
                    )

                    try:
                        authenticator.login()
                    except Exception as e:
                        st.error(e)

                    if st.session_state.get("authentication_status"):
                      authenticator.logout()
                      st.write(f'ようこそ *{st.session_state.get("name")}* さん')
                      username = st.session_state.get("username")
                      user_zip_code = config["credentials"]["usernames"][username]["zip_code"] 
                      user_address = config["credentials"]["usernames"][username]["address"]
                      user_name = config["credentials"]["usernames"][username]["name"] 
                      user_phone_number = config["credentials"]["usernames"][username]["phone_number"] 
                      user_email = config["credentials"]["usernames"][username]["email"]
                      user_customer_number = config["credentials"]["usernames"][username]["customer_number"]
                    else:
                      user_zip_code = ""
                      user_address = ""
                      user_name = ""
                      user_phone_number = ""
                      user_email = ""
                      user_customer_number = ""
                      if st.session_state.get("authentication_status") is False:
                         st.error("UsernameもしくはPasswordが正しくありません")
                      elif st.session_state.get("authentication_status") is None:
                         st.warning("UsernameとPasswordを入力してください")

                    if  user_zip_code and user_address and user_name and user_phone_number and user_email and user_customer_number:
                        zip_code = st.text_input("郵便番号(半角数字・ハイフン無)", value=user_zip_code, placeholder="1234567")
                        address = st.text_input("住所(郵便番号から自動検索)", value=user_address, placeholder="東京都港区海岸1-5-20サンプルマンション202号室")
                        name = st.text_input("お名前", value=user_name, placeholder="東京太郎")
                        phone_number = st.text_input("電話番号(半角数字・ハイフン無)", value=user_phone_number, placeholder="0123456789")
                        email = st.text_input("メールアドレス", value=user_email, placeholder="sample@tokyo-gas.co.jp")
                        customer_number = st.text_input("お客さま番号", value=user_customer_number, placeholder="19999999999")
                        st.markdown("&nbsp;&nbsp;&nbsp;")
                        
                    else:
                        zip_code = st.text_input("郵便番号(半角数字・ハイフン無)", placeholder = "1234567")
                        address = st.text_input("住所(郵便番号から自動検索)", value = get_address(zip_code) if zip_code and len(zip_code) == 7 and zip_code.isdigit() else "", placeholder = "東京都港区海岸1-5-20サンプルマンション202号室")
                        name = st.text_input("お名前", placeholder = "東京太郎")
                        phone_number = st.text_input("電話番号(半角数字・ハイフン無)", placeholder = "0123456789")
                        email = st.text_input("メールアドレス", placeholder = "sample@tokyo-gas.co.jp")
                        customer_number = st.text_input("お客さま番号", placeholder = "19999999999")
                        st.markdown("&nbsp;&nbsp;&nbsp;")
                  
                    if st.button("お客さま情報を登録し、見積もりをする"):
                        if not address or not name or not phone_number or not email or not customer_number:
                            st.error("すべての項目を入力してください。")
                        else:
                            st.markdown("&nbsp;&nbsp;&nbsp;")
                            st.subheader("●見積もり")
                            st.image("model.png")
                            st.write("##### 型番：" + _model)
                            st.write("##### 機器販売価格：" + str(format(price, ",")) + "円")
                            st.write("##### 基本工事費：" + str(format(cost, ",")) + "円")
                            st.write("##### 補助金額：" + str(format(subsidy, ",")) + "pt")
                            st.info("### 実質負担額：" + str(format((price + cost - subsidy), ",")) + "円")
                            st.markdown("&nbsp;&nbsp;&nbsp;")
                            st.write("※補助金の正式名称は東京都が実施する「家庭のゼロエミッション行動推進事業」です。補助金は受給条件・予算枠があり、支給されない場合や上記金額での支給がされない場合があります。")
                            st.write("※補助金の受領には、事前に登録された事業者・店舗にて購入する、都内に住所を有する個人である、その住所を公的な書類（免許証等）で証明できるなどの条件があります。詳しくはこちらをご確認ください。")
                            st.write("https://www.tz-points.jp/system")
            else:
                st.error("Gemini モデルの初期化に失敗しました。")
        else:
            st.error("Gemini モデルの初期化に失敗しました。")

if __name__ == "__main__":
    main()