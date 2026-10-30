/**
 * 검색 필터 옵션 로더
 * 조사연도, 시도, 지도정보 등의 필터 옵션을 동적으로 로드합니다.
 */
(function initFilterOptions() {
    'use strict';

    let filterData = null;

    // config 로드 완료 후 초기화
    window.configReady.then(function() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }
    });

    async function bootstrapMain(){
        await  window.configReady; // api-config.js 로딩 완료 대기
        debugLog('bootstrapMain:', bootstrapMain);
        await loadFilterData();
    }


    function init() {
        bootstrapMain().catch(console.error);
    }

    /**
     * 필터 데이터 로드
     */
    function loadFilterData() {
        const apiUrl = window.getApiUrl('/apihome/map/filter-options');
        debugLog('필터 데이터 로드 URL:', apiUrl);

        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('필터 데이터 로드 실패: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                filterData = data;
                initAllFilters();
            })
            .catch(error => {
                console.error('필터 데이터 로드 오류:', error);
            });
    }

    /**
     * 모든 필터 초기화
     */
    function initAllFilters() {
        initSurveyYearFilter();
        initHouseTypeFilter();
        initRegionFilter();
        initSigunguFilter();  // 시군구 필터 초기화
        initMapInfoTypeFilter();

        // 필터 초기화 완료 후 초기 데이터 로드 이벤트 발생
        if (filterData && filterData.years && filterData.years.length > 0) {
            const latestYear = filterData.years[0].year;
            window.dispatchEvent(new CustomEvent('filterOptionsLoaded', {
                detail: { latestYear: latestYear }
            }));
        }
    }

    /**
     * 시군구 필터 초기화 (초기에는 비활성화)
     */
    function initSigunguFilter() {
        const selectElement = document.getElementById('selectSigungu');
        if (!selectElement) return;

        // 초기화: 비활성화 상태
        selectElement.innerHTML = '<option value="">시도를 먼저 선택하세요</option>';
        selectElement.disabled = true;
        debugLog('시군구 필터 초기화 완료 (비활성화 상태)');
    }

    /**
     * 시군구 옵션 로드 (시도 선택 시 호출)
     * BND_SIGUNGU_PG 테이블에서 조회
     */
    window.loadSigunguOptions = function(year, sidoCode, mapInfo) {
        const selectElement = document.getElementById('selectSigungu');
        if (!selectElement) return;
        
        if (!sidoCode || sidoCode === '') {
            // 전국 선택 시 비활성화
            selectElement.innerHTML = '<option value="">시도를 먼저 선택하세요</option>';
            selectElement.disabled = true;
            return;
        }

        // 센서스 표준 API 호출 (빈집 데이터가 없어도 코드 목록 조회)
        const apiUrl = window.getApiUrl(`/apihome/map/codes/sigungu?sidoCode=${sidoCode}`);
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error('시군구 코드 로드 실패: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                selectElement.innerHTML = '<option value="">전체</option>';

                if (data && Array.isArray(data)) {
                    data.forEach(sigungu => {
                        const option = document.createElement('option');
                        option.value = sigungu.code;
                        option.textContent = sigungu.name;

                        // 위치 정보 추가 (data-lat, data-lng)
                        if (sigungu.lat) option.dataset.lat = sigungu.lat;
                        if (sigungu.lon) option.dataset.lng = sigungu.lon;
                        if (sigungu.lng) option.dataset.lng = sigungu.lng;

                        selectElement.appendChild(option);
                    });

                    selectElement.disabled = false;
                    debugLog('시군구 옵션 로드 완료:', data.length + '개');
                }
            })
            .catch(error => {
                console.error('시군구 옵션 로드 오류:', error);
                selectElement.innerHTML = '<option value="">로드 실패</option>';
            });
    };

    /**
     * 조사연도 필터 초기화
     */
    function initSurveyYearFilter() {
        const selectElement = document.getElementById('selectSurveyYear');
        if (!selectElement || !filterData || !filterData.years) return;

        // 기존 옵션 제거
        selectElement.innerHTML = '';

        // 옵션 추가 (최신연도가 기본값)
        filterData.years.forEach((yearObj, index) => {
            const option = document.createElement('option');
            option.value = yearObj.year;
            option.textContent = (yearObj.year - 1) + '년';

            // 첫 번째(최신) 연도를 기본값으로 설정
            if (index === 0) {
                option.selected = true;
                initState(yearObj.year);
            }

            selectElement.appendChild(option);
        });

        debugLog('조사연도 필터 초기화 완료:', filterData.years.length + '개');
    }

    /**
     * 주택유형 필터 초기화 (state.html용)
     */
    function initHouseTypeFilter() {
        const selectElement = document.getElementById('selectHouseType');
        if (!selectElement || !filterData || !filterData.houseTypes) return;

        // 기존 옵션 제거
        selectElement.innerHTML = '';

        // 주택유형 필터링 (houseTypes가 있는 경우만 처리)
        if (filterData.houseTypes && Array.isArray(filterData.houseTypes)) {
            const activeTypes = filterData.houseTypes.filter(item => {
                return item.USE_YN === 'Y' && item.DEL_YN !== 'Y';
            });

            // 옵션 추가
            activeTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.TYPE_CODE;
                option.textContent = type.TYPE_NAME;

                // 기본값 설정
                if (type.IS_DEFAULT === 'Y') {
                    option.selected = true;
                }

                selectElement.appendChild(option);
            });

            debugLog('주택유형 필터 초기화 완료:', activeTypes.length + '개');
        }
    }

    /**
     * 시도 필터 초기화 (map.html용)
     */
    function initRegionFilter() {
        const selectElement = document.getElementById('selectRegion');
        if (!selectElement || !filterData || !filterData.regions) return;

        // 기존 옵션 제거
        selectElement.innerHTML = '';

        // 옵션 추가
        filterData.regions.forEach(region => {
            const option = document.createElement('option');
            option.value = region.sreg;
            option.textContent = region.regNm;

            // 위치 정보 추가 (data-lat, data-lng)
            // 백엔드에서 lon으로 반환하므로 lng로 변환
            if (region.lat) option.dataset.lat = region.lat;
            if (region.lon) option.dataset.lng = region.lon;
            if (region.lng) option.dataset.lng = region.lng;

            // 전국을 기본값으로 설정
            if (region.sreg === '') {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });

        debugLog('시도 필터 초기화 완료:', filterData.regions.length + '개');
    }

    /**
     * 지도정보 필터 초기화 (map.html용)
     */
    function initMapInfoTypeFilter() {
        const selectElement = document.getElementById('selectMapInfo');
        if (!selectElement || !filterData || !filterData.mapInfoTypes) return;

        // 기존 옵션 제거
        selectElement.innerHTML = '';

        // 옵션 추가
        filterData.mapInfoTypes.forEach(type => {
            const option = document.createElement('option');
            option.value = type.typeCode;
            option.textContent = type.typeName;

            // 기본값 설정
            if (type.isDefault === true) {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });

        debugLog('지도정보 필터 초기화 완료:', filterData.mapInfoTypes.length + '개');
    }

})();
