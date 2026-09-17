import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제의 박스오피스")


# ---------------------------------------------------------
# 2. 한국 시간 기준으로 '어제' 날짜 계산
# 배포 서버의 시간이 한국 시간이 아닐 수 있기 때문에
# Asia/Seoul 시간대를 직접 지정한다.
# ---------------------------------------------------------
korea_now = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday = korea_now.date() - timedelta(days=1)

# API에서 사용하는 날짜 형식: yyyymmdd
target_date = yesterday.strftime("%Y%m%d")

# 화면에 보여 줄 날짜 형식
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.write(f"📅 **{display_date} 박스오피스 순위**")


# ---------------------------------------------------------
# 3. KOBIS API에서 데이터를 가져오는 함수
#
# @st.cache_data(ttl=3600)
# → 같은 날짜의 데이터를 다시 요청하면 API를 다시 호출하지 않고
#   최대 1시간 동안 저장된 데이터를 사용한다.
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_boxoffice_data(target_dt):
    # Streamlit Cloud의 비밀 금고에서 인증키를 가져온다.
    # 코드 안에 API 키를 직접 적지 않는다.
    api_key = st.secrets["KOBIS_KEY"]

    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_dt
    }

    try:
        # KOBIS 서버에 데이터 요청
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        # HTTP 요청 자체가 실패한 경우 오류 발생
        response.raise_for_status()

        # JSON 형태로 변환
        data = response.json()

    except requests.exceptions.Timeout:
        return None, (
            "KOBIS 서버의 응답 시간이 너무 오래 걸렸습니다. "
            "잠시 후 다시 시도해 주세요."
        )

    except requests.exceptions.RequestException as e:
        return None, (
            "KOBIS API 요청에 실패했습니다.\n\n"
            "인터넷 연결이나 KOBIS 서버 상태를 확인해 주세요.\n\n"
            f"오류 내용: {e}"
        )

    except ValueError:
        return None, (
            "KOBIS 서버에서 정상적인 JSON 데이터를 받지 못했습니다. "
            "잠시 후 다시 시도해 주세요."
        )

    # -----------------------------------------------------
    # 인증키가 잘못된 경우에도 HTTP 상태코드가 200일 수 있다.
    # 이 경우 응답 안에 faultInfo가 들어온다.
    # -----------------------------------------------------
    if "faultInfo" in data:
        fault_info = data["faultInfo"]

        message = fault_info.get(
            "message",
            "알 수 없는 API 오류가 발생했습니다."
        )

        return None, (
            "KOBIS API에서 오류를 반환했습니다.\n\n"
            f"오류 내용: {message}\n\n"
            "Streamlit Secrets에 `KOBIS_KEY`가 올바르게 등록되어 있는지 "
            "확인해 주세요."
        )

    # -----------------------------------------------------
    # 필요한 영화 목록 꺼내기
    # -----------------------------------------------------
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError):
        return None, (
            "KOBIS 응답에서 박스오피스 데이터를 찾을 수 없습니다.\n\n"
            "API 응답 구조가 변경되었거나 일시적인 서버 문제가 "
            "발생했는지 확인해 주세요."
        )

    # 영화 목록이 비어 있는 경우
    if not movie_list:
        return None, (
            "해당 날짜의 박스오피스 데이터가 없습니다.\n\n"
            "조회 날짜가 아직 집계되지 않았거나 KOBIS에서 데이터를 "
            "제공하지 않는 날짜인지 확인해 주세요."
        )

    return movie_list, None


# ---------------------------------------------------------
# 4. 데이터 가져오기
# ---------------------------------------------------------
try:
    movie_list, error_message = get_boxoffice_data(target_date)

except KeyError:
    # secrets에 KOBIS_KEY가 없을 경우
    st.error(
        "KOBIS 인증키를 찾을 수 없습니다.\n\n"
        "Streamlit Cloud의 **Settings → Secrets**에서 "
        "`KOBIS_KEY`가 등록되어 있는지 확인해 주세요."
    )
    st.stop()

except Exception as e:
    st.error(
        "데이터를 불러오는 중 예상하지 못한 오류가 발생했습니다.\n\n"
        f"오류 내용: {e}"
    )
    st.stop()


# API에서 오류가 발생했다면 안내 후 앱 실행 중단
if error_message:
    st.error(error_message)
    st.stop()


# ---------------------------------------------------------
# 5. DataFrame으로 변환
# ---------------------------------------------------------
df = pd.DataFrame(movie_list)


# ---------------------------------------------------------
# 6. 숫자로 전달되어야 하지만 API에서는 문자열로 오는 값들을
# 실제 숫자형으로 변환한다.
#
# 이렇게 해야 올바른 정렬과 그래프 작성이 가능하다.
# ---------------------------------------------------------
numeric_columns = [
    "rank",
    "rankInten",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt"
]

for column in numeric_columns:
    if column in df.columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        ).fillna(0).astype(int)


# 순위를 기준으로 정렬
df = df.sort_values("rank").reset_index(drop=True)


# ---------------------------------------------------------
# 7. 1위 영화 정보 표시
# ---------------------------------------------------------
first_place_df = df[df["rank"] == 1]

# 혹시 rank == 1 데이터가 없다면 첫 번째 데이터를 대신 사용
if not first_place_df.empty:
    first_movie = first_place_df.iloc[0]
else:
    first_movie = df.iloc[0]


st.divider()

st.subheader(f"🏆 박스오피스 1위 · {first_movie['movieNm']}")

# 세 개의 지표 카드를 가로로 배치
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="어제 관객수",
        value=f"{first_movie['audiCnt']:,}명"
    )

with col2:
    st.metric(
        label="누적 관객수",
        value=f"{first_movie['audiAcc']:,}명"
    )

with col3:
    st.metric(
        label="스크린수",
        value=f"{first_movie['scrnCnt']:,}개"
    )


# ---------------------------------------------------------
# 8. 전체 박스오피스 표
# ---------------------------------------------------------
st.divider()

st.subheader("📋 전체 박스오피스 순위")


# 사용자에게 보여 줄 열만 선택
table_df = df[
    [
        "rank",
        "movieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]
].copy()


# 열 이름을 보기 좋은 한국어로 변경
table_df = table_df.rename(
    columns={
        "rank": "순위",
        "movieNm": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수"
    }
)


# Streamlit 표 출력
st.dataframe(
    table_df,
    width="stretch",
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d위"
        ),
        "영화명": st.column_config.TextColumn(
            "영화명"
        ),
        "개봉일": st.column_config.TextColumn(
            "개봉일"
        ),
        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="%d명"
        ),
        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="%d명"
        ),
        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="%d개"
        )
    }
)


# ---------------------------------------------------------
# 9. 관객수 상위 5편 막대그래프
#
# rank 순서가 아니라 실제 관객수를 기준으로 다시 정렬한다.
# ---------------------------------------------------------
st.divider()

st.subheader("📊 관객수 상위 5편")


top5 = (
    df.sort_values(
        "audiCnt",
        ascending=False
    )
    .head(5)
    [["movieNm", "audiCnt"]]
    .copy()
)


# 그래프에서는 관객수가 많은 영화부터 보이도록 정렬
top5 = top5.sort_values(
    "audiCnt",
    ascending=False
)


# 영화명을 인덱스로 설정
top5_chart = top5.set_index("movieNm")


st.bar_chart(
    top5_chart,
    y="audiCnt",
    x_label="영화",
    y_label="관객수"
)


# ---------------------------------------------------------
# 10. 하단 안내
# ---------------------------------------------------------
st.caption(
    "자료 출처: 영화진흥위원회 KOBIS 영화관입장권통합전산망"
)
