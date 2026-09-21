```python
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="KOBIS 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 일일 박스오피스")


# ---------------------------------------------------------
# 2. 한국 시간 기준 날짜 계산
# ---------------------------------------------------------
# 배포 서버의 시간이 한국 시간이 아닐 수 있으므로
# 한국 시간(Asia/Seoul)을 직접 지정한다.
korea_today = datetime.now(ZoneInfo("Asia/Seoul")).date()

# 오늘은 아직 집계가 끝나지 않았으므로
# 가장 최근에 선택할 수 있는 날짜는 어제이다.
max_date = korea_today - timedelta(days=1)

# KOBIS에서 제공하는 일일 박스오피스의 시작 날짜를
# 넉넉하게 설정한다.
min_date = datetime(2000, 1, 1).date()


# ---------------------------------------------------------
# 3. 조회 날짜 선택
# ---------------------------------------------------------
st.subheader("📅 조회 날짜")

selected_date = st.date_input(
    "박스오피스를 확인할 날짜를 선택하세요.",
    value=max_date,
    min_value=min_date,
    max_value=max_date
)

# API에서 사용하는 날짜 형식: YYYYMMDD
target_date = selected_date.strftime("%Y%m%d")

# 화면에 표시할 날짜
display_date = selected_date.strftime("%Y년 %m월 %d일")


# ---------------------------------------------------------
# 4. KOBIS API에서 박스오피스 데이터를 가져오는 함수
# ---------------------------------------------------------
# 같은 날짜를 다시 조회하면 1시간 동안 저장된 결과를 사용한다.
@st.cache_data(ttl=3600)
def get_boxoffice_data(target_dt):

    # Streamlit Cloud의 Secrets에서 API 인증키를 가져온다.
    # API 키를 코드에 직접 작성하지 않는다.
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
        # KOBIS API 요청
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        # HTTP 요청 자체가 실패했는지 확인
        response.raise_for_status()

        # JSON 데이터로 변환
        data = response.json()

    except requests.exceptions.Timeout:
        return None, (
            "KOBIS 서버의 응답 시간이 너무 오래 걸렸습니다.\n\n"
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
            "KOBIS 서버에서 정상적인 JSON 데이터를 받지 못했습니다.\n\n"
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
            "Streamlit Cloud의 Secrets에 "
            "`KOBIS_KEY`가 올바르게 등록되어 있는지 확인해 주세요."
        )

    # -----------------------------------------------------
    # 박스오피스 영화 목록 가져오기
    # -----------------------------------------------------
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]

    except (KeyError, TypeError):
        return None, (
            "KOBIS 응답에서 박스오피스 데이터를 찾을 수 없습니다.\n\n"
            "KOBIS API의 응답 구조가 변경되었거나 "
            "일시적인 서버 문제가 발생했는지 확인해 주세요."
        )

    # 영화 목록이 비어 있는 경우
    if not movie_list:
        return None, "그날은 아직 집계 전입니다"

    return movie_list, None


# ---------------------------------------------------------
# 5. 데이터 가져오기
# ---------------------------------------------------------
try:
    movie_list, error_message = get_boxoffice_data(target_date)

except KeyError:
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


# 오류가 발생했다면 메시지를 보여주고 종료
if error_message:

    if error_message == "그날은 아직 집계 전입니다":
        st.warning("📢 그날은 아직 집계 전입니다.")

    else:
        st.error(error_message)

    st.stop()


# ---------------------------------------------------------
# 6. DataFrame으로 변환
# ---------------------------------------------------------
df = pd.DataFrame(movie_list)


# ---------------------------------------------------------
# 7. 숫자로 변환
# KOBIS API에서는 숫자도 문자열로 전달된다.
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
# 8. 순위 증감 표시 만들기
# ---------------------------------------------------------
def make_rank_change(rank_inten):

    # 양수 = 전날보다 순위가 올라감
    if rank_inten > 0:
        return f"🔺 {rank_inten}"

    # 음수 = 전날보다 순위가 내려감
    elif rank_inten < 0:
        return f"🔻 {abs(rank_inten)}"

    # 0 = 순위 변동 없음
    else:
        return "-"


# 표에 표시할 순위 증감 문자열
df["순위증감"] = df["rankInten"].apply(make_rank_change)


# ---------------------------------------------------------
# 9. 누적관객 100만 명 이상이면 트로피 표시
# ---------------------------------------------------------
def make_movie_name(row):

    movie_name = row["movieNm"]
    cumulative_audience = row["audiAcc"]

    # 누적관객이 100만 명 이상이면 트로피 추가
    if cumulative_audience >= 1_000_000:
        return f"🏆 {movie_name}"

    return movie_name


df["표시영화명"] = df.apply(
    make_movie_name,
    axis=1
)


# ---------------------------------------------------------
# 10. 선택한 날짜 표시
# ---------------------------------------------------------
st.divider()

st.subheader(f"📅 {display_date} 박스오피스")


# ---------------------------------------------------------
# 11. 1위 영화 정보
# ---------------------------------------------------------
first_place_df = df[df["rank"] == 1]

if not first_place_df.empty:
    first_movie = first_place_df.iloc[0]
else:
    first_movie = df.iloc[0]


st.subheader(
    f"🏆 박스오피스 1위 · {first_movie['표시영화명']}"
)


# 세 개의 지표 카드를 가로로 배치
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="관객수",
        value=f"{first_movie['audiCnt']:,}명"
    )

with col2:
    st.metric(
        label="누적관객",
        value=f"{first_movie['audiAcc']:,}명"
    )

with col3:
    st.metric(
        label="스크린수",
        value=f"{first_movie['scrnCnt']:,}개"
    )


# ---------------------------------------------------------
# 12. 전체 박스오피스 표
# ---------------------------------------------------------
st.divider()

st.subheader("📋 전체 박스오피스")


table_df = df[
    [
        "rank",
        "표시영화명",
        "openDt",
        "순위증감",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]
].copy()


# 열 이름을 한국어로 변경
table_df = table_df.rename(
    columns={
        "rank": "순위",
        "표시영화명": "영화명",
        "openDt": "개봉일",
        "순위증감": "전일대비",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수"
    }
)


# 표 출력
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
        "전일대비": st.column_config.TextColumn(
            "전일대비"
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
# 13. 관객수 상위 5편 그래프
# ---------------------------------------------------------
st.divider()

st.subheader("📊 관객수 상위 5편")


top5 = (
    df.sort_values(
        "audiCnt",
        ascending=False
    )
    .head(5)
    [["표시영화명", "audiCnt"]]
    .copy()
)


# 그래프용 인덱스 설정
top5_chart = top5.set_index("표시영화명")


st.bar_chart(
    top5_chart,
    y="audiCnt",
    x_label="영화",
    y_label="관객수"
)


# ---------------------------------------------------------
# 14. 데이터 출처
# ---------------------------------------------------------
st.caption(
    "자료 출처: 영화진흥위원회 KOBIS 영화관입장권통합전산망"
)
```
