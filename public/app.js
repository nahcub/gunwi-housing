/* 군위군 빈집·노후주택 주거환경 취약지역 분석 — 화면 로직
 *
 * 데이터는 빌드 때 HTML에 박아넣지 않고 런타임에 fetch한다.
 * public/data/* 는 tools/build.py 가 생성한다 — 직접 고치지 말 것.
 *
 * 조인은 코드로만 한다(읍면 region_code, 리 ri_code). 지역명 매칭은 tools/prepare.py 가
 * 빌드 시점에 이미 끝내놨다. 공간 단위는 읍면 8개 / 법정리 92개 두 가지다.
 */
'use strict';

const RAMP = ['#eaf1f8', '#c3d9ec', '#8fb9dc', '#5b95c6', '#2f6fb0'];
const state = { unit: 'eupmyeon', period: null, indicator: null, selected: null, sourceFilter: 'all' };
const UNIT_LABEL = { eupmyeon: '읍면', ri: '리' };
const store = {};
let map, layer, labels;

const $ = (id) => document.getElementById(id);

async function getJSON(path) {
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

/* ------------------------------------------------------------------ 조회 */

const rows = () => (state.unit === 'ri'
  ? store.regions.ri
  : store.regions.regions[state.period] || []);
const codeOf = (row) => (state.unit === 'ri' ? row.ri_code : row.region_code);
const featureCode = (f) => (state.unit === 'ri' ? f.properties.ri_code : f.properties.region_code);
const boundaryFor = () => (state.unit === 'ri' ? store.riBoundary : store.boundary);
const indicatorsForUnit = () =>
  store.regions.indicators.filter((i) => (i.units || ['eupmyeon']).includes(state.unit));
const indicatorById = (id) => store.regions.indicators.find((i) => i.id === id);
const rowByCode = (code) => rows().find((r) => codeOf(r) === code);

function valueOf(row) {
  const v = row[state.indicator];
  return typeof v === 'number' ? v : null;
}

function scale() {
  const vals = rows().map(valueOf).filter((v) => v !== null);
  const min = Math.min(...vals), max = Math.max(...vals);
  return { min, max, span: max - min || 1 };
}

function colorOf(row) {
  const v = valueOf(row);
  if (v === null) return '#e9ecef';
  const { min, span } = scale();
  const i = Math.min(RAMP.length - 1, Math.floor(((v - min) / span) * RAMP.length));
  return RAMP[i];
}

function fmt(v, unit) {
  if (v === null || v === undefined) return '—';
  const n = ['명', 'm', '동'].includes(unit) ? v.toLocaleString('ko-KR') : v;
  return `${n}${unit ? ' ' + unit : ''}`;
}

/* -------------------------------------------------------------- 상단 배너 */

function renderBanner() {
  const p = store.boundary._provenance;
  if (!p || p === 'verified') return;
  const el = $('provenance-banner');
  el.hidden = false;
  el.innerHTML =
    '<strong>경계 데이터 출처 미확인</strong> — 이 지도의 읍면 경계는 다운로드 ' +
    '이력이 기록되지 않은 파일입니다. SGIS에서 재취득해 대조하기 전까지 ' +
    '경계 자체를 검증된 자료로 인용하지 마세요. ' +
    '(<code>data/raw/boundary-eupmyeon-2025-06-30/_meta.json</code>)';
}

function renderSubtitle() {
  const ref = store.regions.meta.reference_dates[state.period];
  const ind = indicatorById(state.indicator);
  // 시설·SGIS 지표는 인구 시점과 기준일이 다르다
  const indRef = ind.reference ? ` (지표 기준 ${ind.reference})` : '';
  $('subtitle').textContent =
    `기준시점 ${ref} · 표시 지표: ${ind.label}${indRef} · ${UNIT_LABEL[state.unit]} ${rows().length}개 · ` +
    `생성 ${store.regions.meta.generated_at}`;
}

/* ---------------------------------------------------------------- 사이드 */

// 한 시점 진단이다(분석 기준 시점 하나). 인구 변화 지표만 기준 시점 대비로 계산돼 있다
function renderPeriodNote() {
  const m = store.regions.meta;
  $('period-note').textContent =
    `분석 기준 ${m.reference_dates[m.analysis_period]} (주민등록 인구). ` +
    `인구 변화 지표는 ${m.reference_dates[m.baseline_period]} 대비 ${m.change_months}개월 변화. ` +
    '시설·통계 지표는 지표별 기준일을 따른다.';
}

function renderUnits() {
  const box = $('unit-tabs');
  box.innerHTML = '';
  [['eupmyeon', '읍면 8개'], ['ri', '법정리 92개']].forEach(([u, label]) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.setAttribute('aria-pressed', String(u === state.unit));
    b.onclick = () => setUnit(u);
    box.appendChild(b);
  });
  $('unit-note').textContent = state.unit === 'ri'
    ? '리 단위는 주거용 건물(GIS건물통합정보 2026-09-09) 기반 지표와 경로당 수만 있다. ' +
      '인구·고령화는 리별 자료가 없어 읍면에서만 볼 수 있다. 값은 리별 집계이며 집 단위 값은 공개하지 않는다.'
    : '';
}

function setUnit(u) {
  if (u === state.unit) return;
  state.unit = u;
  state.selected = null;
  if (!indicatorsForUnit().some((i) => i.id === state.indicator && i.status === 'available')) {
    state.indicator = indicatorsForUnit().find((i) => i.status === 'available').id;
  }
  buildAreaLayer();
  renderUnits();
  redraw();
}

function renderIndicators() {
  const ul = $('indicator-list');
  ul.innerHTML = '';
  indicatorsForUnit().forEach((ind) => {
    const li = document.createElement('li');
    const b = document.createElement('button');
    const available = ind.status === 'available';

    b.disabled = !available;
    b.setAttribute('aria-pressed', String(ind.id === state.indicator));
    b.innerHTML =
      `${ind.label}<span class="badge">${
        available ? ind.unit : ind.status === 'blocked' ? '보류' : '미확보'
      }</span>`;

    if (!available) {
      const why = document.createElement('span');
      why.className = 'why';
      why.textContent = ind.reason
        ? ind.reason
        : `원자료 미확보 (${ind.blocked_by})`;
      b.appendChild(why);
    }
    b.onclick = () => { state.indicator = ind.id; redraw(); };
    li.appendChild(b);
    ul.appendChild(li);
  });
}

function renderRanking() {
  const ind = indicatorById(state.indicator);
  const ol = $('ranking');
  ol.innerHTML = '';
  const { min, span } = scale();
  $('ranking-title').textContent = `${UNIT_LABEL[state.unit]} 순위`;
  const sorted = [...rows()].sort((a, b) => (valueOf(b) ?? -Infinity) - (valueOf(a) ?? -Infinity));

  sorted.forEach((r) => {
    const v = valueOf(r);
    const li = document.createElement('li');
    li.setAttribute('aria-current', String(codeOf(r) === state.selected));
    li.onclick = () => select(codeOf(r), true);
    const label = state.unit === 'ri' ? `${r.region_name} ${r.name}` : r.name;
    li.innerHTML =
      `<span style="flex:0 0 ${state.unit === 'ri' ? 120 : 72}px">${label}</span>` +
      `<span class="bar"><span style="width:${
        v === null ? 0 : Math.max(4, ((v - min) / span) * 100)
      }%;background:${colorOf(r)}"></span></span>` +
      `<span class="val">${fmt(v, ind.unit)}</span>`;
    ol.appendChild(li);
  });
}

function renderDetail() {
  const card = $('detail-card');
  if (!state.selected) { card.hidden = true; return; }
  const r = rowByCode(state.selected);
  if (!r) { card.hidden = true; return; }
  card.hidden = false;

  const km = (m) => (m === null || m === undefined ? '—' : `${(m / 1000).toFixed(1)} km`);
  const housingRows =
    `<dt>주거용 건물</dt><dd>${r.houses.toLocaleString('ko-KR')} 동</dd>` +
    `<dt>노후주택</dt><dd>${r.old_house_ratio} % (확인분 ${r.old_house_confirmed_ratio} %, 사용승인일 빈칸 ${r.approval_blank_ratio} %)</dd>` +
    `<dt>1차 의료 거리</dt><dd>평균 ${km(r.primary_care_mean_m)}, 2km 밖 ${r.primary_care_far_pct} %</dd>` +
    `<dt>보건기관 / 의원</dt><dd>평균 ${km(r.health_mean_m)} / ${km(r.clinic_mean_m)}</dd>` +
    `<dt>약국 거리</dt><dd>평균 ${km(r.pharmacy_mean_m)}</dd>`;
  if (state.unit === 'ri') {
    $('detail').innerHTML =
      `<div class="name">${r.region_name} ${r.name}</div>` +
      '<dl>' + housingRows +
      `<dt>경로당</dt><dd>${r.senior_center_count} 개소 (리 안)</dd>` +
      `<dt>법정리코드</dt><dd>${r.ri_code}</dd>` +
      '</dl>';
    return;
  }
  $('detail').innerHTML =
    `<div class="name">${r.name}</div>` +
    '<dl>' +
    `<dt>총인구</dt><dd>${r.population.toLocaleString('ko-KR')} 명</dd>` +
    `<dt>65세 이상</dt><dd>${r.elderly.toLocaleString('ko-KR')} 명</dd>` +
    `<dt>고령화율</dt><dd>${r.elderly_ratio} % (${r.elderly_ratio_change >= 0 ? '+' : ''}${r.elderly_ratio_change}%p)</dd>` +
    `<dt>인구 변화</dt><dd>${r.population_baseline.toLocaleString('ko-KR')} → ` +
    `${r.population.toLocaleString('ko-KR')} 명 (${r.pop_change_rate}%, 연 ${r.pop_change_rate_annual}%)</dd>` +
    housingRows +
    `<dt>노령화지수</dt><dd>${r.aging_index}</dd>` +
    `<dt>경로당</dt><dd>${r.senior_center_count} 개소 (노후 ${r.senior_center_old_count}, ${r.senior_center_old_ratio}%)</dd>` +
    `<dt>고령 1천명당 경로당</dt><dd>${r.senior_center_per_1k_elderly} 개소</dd>` +
    `<dt>행정기관코드</dt><dd>${r.region_code}</dd>` +
    '</dl>';
}

function renderLegend() {
  const ind = indicatorById(state.indicator);
  const { min, max } = scale();
  const step = (max - min) / RAMP.length;
  const parts = RAMP.map((c, i) => {
    const lo = min + step * i;
    const hi = i === RAMP.length - 1 ? max : min + step * (i + 1);
    const round = (x) => (['명', 'm'].includes(ind.unit) ? Math.round(x).toLocaleString('ko-KR')
                                                        : x.toFixed(1));
    return `<span><span class="swatch" style="background:${c}"></span>` +
           `${round(lo)} ~ ${round(hi)}</span>`;  // 음수 구간에서 '–' 가 부호와 헷갈린다
  });
  $('legend').innerHTML =
    parts.join('') +
    `<span style="flex-basis:100%">· ${ind.label} (${ind.unit}) — ` +
    `구간은 현재 화면의 ${UNIT_LABEL[state.unit]} ${rows().length}개 값에 대한 상대 척도입니다(절대 기준이 아님).</span>`;
}

function renderSources() {
  const ul = $('sources');
  ul.innerHTML = '';
  const cls = (s) => s === '확보' ? 'st-ok'
    : s === '미확보' || s === '출처미확인' ? 'st-missing' : 'st-partial';

  const list = store.sources.sources.filter((s) => {
    if (state.sourceFilter === 'all') return true;
    if (state.sourceFilter === 'missing') return s.status === '미확보' || s.status === '출처미확인';
    return s.status.startsWith('확보') || s.status === '부분확보';
  });

  list.forEach((s) => {
    const li = document.createElement('li');
    const link = s.url
      ? `<a href="${s.url}" target="_blank" rel="noopener">출처</a>`
      : '<span style="color:#9ca3af">링크 없음</span>';
    li.innerHTML =
      `<div><strong>${s.name}</strong>` +
      `<span class="st ${cls(s.status)}">${s.status}</span></div>` +
      `<div class="meta">${s.provider} · 기준 ${s.reference_date || '미정'} · ` +
      `라이선스: ${s.license} · ${link}</div>` +
      `<div class="meta">${s.notes || ''}</div>`;
    ul.appendChild(li);
  });
}

function renderSourceFilters() {
  const box = $('source-filters');
  box.innerHTML = '';
  [['all', '전체'], ['have', '확보'], ['missing', '미확보']].forEach(([k, label]) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.setAttribute('aria-pressed', String(k === state.sourceFilter));
    b.onclick = () => { state.sourceFilter = k; renderSourceFilters(); renderSources(); };
    box.appendChild(b);
  });
}

/* ------------------------------------------------------------------ 지도 */

function styleFor(feature) {
  const code = featureCode(feature);
  const row = rowByCode(code);
  return {
    fillColor: row ? colorOf(row) : '#e9ecef',
    fillOpacity: 0.85,
    color: state.unit === 'ri' ? '#f8fafc' : '#ffffff',
    weight: code === state.selected ? 3 : state.unit === 'ri' ? 0.8 : 1.5,
  };
}

// 현재 공간 단위의 경계 레이어를 (다시) 만든다. 리는 92개라 이름은 마우스를 올렸을 때만 보인다
function buildAreaLayer() {
  if (layer) map.removeLayer(layer);
  layer = L.geoJSON(boundaryFor(), {
    style: styleFor,
    onEachFeature: (feature, lyr) => {
      lyr.on('click', () => select(featureCode(feature), false));
      if (state.unit === 'ri') {
        const p = feature.properties;
        lyr.bindTooltip(`${p.region_name} ${p.ri_name}`, { sticky: true });
      }
    },
  });
  layer.addTo(map);
  layer.bringToBack();
}

function initMap() {
  map = L.map('map', { zoomControl: true, attributionControl: true });

  // 뷰(center/zoom)를 먼저 잡은 뒤에 레이어를 올린다.
  // 순서가 뒤바뀌면 Leaflet 이 center 없이 투영을 시도해 NaN LatLng 로 터진다.
  const eupLayer = L.geoJSON(store.boundary);
  map.fitBounds(eupLayer.getBounds(), { padding: [12, 12] });
  buildAreaLayer();

  // 읍면 이름은 어느 단위에서든 위치 기준으로 둔다
  labels = L.layerGroup(
    eupLayer.getLayers().map((lyr) => {
      const name = lyr.feature.properties.region_name;
      return L.marker(lyr.getBounds().getCenter(), {
        interactive: false,
        icon: L.divIcon({ className: 'area-label', html: name }),
      });
    })
  ).addTo(map);

  const sc = store.facilities.senior_centers;
  const seniorLayer = L.layerGroup(
    sc.points.map((p) =>
      L.circleMarker([p.lat, p.lon], {
        radius: 4, color: '#4c1d95', weight: 1,
        // 노후(임시 기준) 경로당은 진하게
        fillColor: p.built_year < sc.old_before_year ? '#7c3aed' : '#c4b5fd',
        fillOpacity: 0.9,
      }).bindTooltip(`경로당 · ${p.name} · ${p.built_year}년 건립`))
  );

  L.control.layers(null, {
    '읍면 이름': labels,
    [`경로당 ${sc.points.length}곳 (진한 색: ${sc.old_before_year}년 이전 건립)`]: seniorLayer,
  }, { collapsed: false }).addTo(map);
}

function select(code, fromList) {
  state.selected = state.selected === code ? null : code;
  layer.setStyle(styleFor);
  renderRanking();
  renderDetail();
  if (!fromList && state.selected) {
    const lyr = layer.getLayers().find(
      (l) => featureCode(l.feature) === state.selected);
    if (lyr) map.fitBounds(lyr.getBounds(), { padding: [40, 40] });
  }
}

/* ------------------------------------------------------------------ 구동 */

function redraw() {
  renderSubtitle();
  renderIndicators();
  renderLegend();
  renderRanking();
  renderDetail();
  if (layer) layer.setStyle(styleFor);
}

async function main() {
  const [regions, boundary, riBoundary, facilities, sources] = await Promise.all([
    getJSON('./data/regions.json'),
    getJSON('./data/eupmyeon.geojson'),
    getJSON('./data/ri_boundary.geojson'),
    getJSON('./data/facilities.json'),
    getJSON('./data/sources.json'),
  ]);
  Object.assign(store, { regions, boundary, riBoundary, facilities, sources });
  if (riBoundary.features.length !== regions.ri.length) {
    throw new Error(`리 경계 ${riBoundary.features.length}개 vs 리 지표 ${regions.ri.length}행`);
  }

  if (boundary.features.length !== 8) {
    throw new Error(`읍면 경계가 8개가 아님: ${boundary.features.length}`);
  }
  const missing = boundary.features
    .map((f) => f.properties.region_code)
    .filter((c) => !regions.regions[regions.meta.default_period]
      .some((r) => r.region_code === c));
  if (missing.length) {
    throw new Error(`데이터에 없는 경계 코드: ${missing.join(', ')}`);
  }

  state.period = regions.meta.default_period;
  state.indicator = regions.indicators.find((i) => i.status === 'available').id;

  renderBanner();
  renderPeriodNote();
  renderUnits();
  initMap();
  renderSourceFilters();
  renderSources();
  redraw();
}

main().catch((err) => {
  document.body.insertAdjacentHTML('afterbegin',
    `<div id="provenance-banner" style="background:#fdecec;border-color:#e0a0a0;
     color:#9b2c2c">데이터를 불러오지 못했습니다: ${err.message}<br>
     <code>python tools/build.py</code> 를 먼저 실행했는지 확인하세요.</div>`);
  console.error(err);
});
