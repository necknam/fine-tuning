/** @OnlyCurrentDoc */
const GP_CALENDAR_BOOK = '1Rt2zvnjizTrMyI4RPdBcMrO6mR_EnbdMahnXjRKdabw';
const GP_CALENDAR_SHEET = 794346946;
const GP_CALENDAR_FIELDS = ['입사일', '현 부서 시작일', '입학일', '졸업일'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('날짜 선택')
    .addItem('선택한 셀의 달력 열기', 'showDateCalendar').addToUi();
}

function calendarLabel_(text) {
  return String(text).replace(/[★*]/g, '').trim();
}

function calendarIso_(value, zone) {
  if (value === '') return '';
  if (!(value instanceof Date) || isNaN(value.getTime())) {
    throw new Error('현재 셀에 날짜가 아닌 값이 있습니다. 원문을 확인하세요.');
  }
  return Utilities.formatDate(value, zone, 'yyyy-MM-dd');
}

function calendarParts_(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error('날짜 형식을 확인하세요.');
  const y = Number(match[1]), m = Number(match[2]), d = Number(match[3]);
  const check = new Date(Date.UTC(y, m - 1, d));
  if (y < 1900 || y > 9999 || check.getUTCFullYear() !== y ||
      check.getUTCMonth() + 1 !== m || check.getUTCDate() !== d) {
    throw new Error('존재하지 않는 날짜입니다.');
  }
  return {year: y, month: m, day: d};
}

function showDateCalendar() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getId() !== GP_CALENDAR_BOOK) throw new Error('대상 입력 시트에서 실행하세요.');
  const cell = ss.getActiveRange(), sheet = cell.getSheet();
  const key = calendarLabel_(sheet.getRange(cell.getRow(), 1).getDisplayValue());
  if (sheet.getSheetId() !== GP_CALENDAR_SHEET || cell.getNumRows() !== 1 ||
      cell.getNumColumns() !== 1 || cell.getColumn() < 4 || cell.getColumn() > 8 ||
      GP_CALENDAR_FIELDS.indexOf(key) < 0 || cell.getFormula()) {
    SpreadsheetApp.getUi().alert('팀원입력 탭에서 입사일·현 부서 시작일·입학일·졸업일의 D~H 중 한 셀을 선택하세요.');
    return;
  }
  const zone = ss.getSpreadsheetTimeZone();
  const baseline = calendarIso_(cell.getValue(), zone);
  const today = Utilities.formatDate(new Date(), zone, 'yyyy-MM-dd');
  const token = Utilities.getUuid();
  const target = {row: cell.getRow(), col: cell.getColumn(), key: key,
    baseline: baseline, sheetId: sheet.getSheetId()};
  CacheService.getUserCache().put('gp-calendar:' + token, JSON.stringify(target), 600);
  const template = HtmlService.createTemplateFromFile('Calendar');
  template.contextJson = JSON.stringify({token: token, date: baseline || today, today: today,
    title: key, cell: cell.getA1Notation(), person: sheet.getRange(4, cell.getColumn()).getDisplayValue()})
    .replace(/</g, '\\u003c');
  SpreadsheetApp.getUi().showModalDialog(template.evaluate().setWidth(410).setHeight(640), '날짜 선택');
}

function saveCalendarDate(token, iso) {
  calendarParts_(iso);
  const cache = CacheService.getUserCache();
  const stored = cache.get('gp-calendar:' + String(token));
  if (!stored) throw new Error('달력 유효시간이 지났습니다. 다시 열어주세요.');
  const target = JSON.parse(stored);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getId() !== GP_CALENDAR_BOOK) throw new Error('대상 시트가 다릅니다.');
  const lock = LockService.getDocumentLock();
  lock.waitLock(5000);
  try {
    const sheet = ss.getSheetById(target.sheetId);
    if (!sheet || sheet.getSheetId() !== GP_CALENDAR_SHEET) throw new Error('입력 탭을 찾을 수 없습니다.');
    const cell = sheet.getRange(target.row, target.col);
    const key = calendarLabel_(sheet.getRange(target.row, 1).getDisplayValue());
    if (target.col < 4 || target.col > 8 || key !== target.key || GP_CALENDAR_FIELDS.indexOf(key) < 0 || cell.getFormula()) {
      throw new Error('입력 위치가 바뀌었습니다. 셀을 다시 선택하세요.');
    }
    const zone = ss.getSpreadsheetTimeZone();
    if (calendarIso_(cell.getValue(), zone) !== target.baseline) {
      throw new Error('다른 사용자가 날짜를 변경했습니다. 다시 열어 확인하세요.');
    }
    const labels = sheet.getRange(1, 1, sheet.getLastRow(), 1).getDisplayValues().map(r => calendarLabel_(r[0]));
    const pair = key === '입사일' ? ['현 부서 시작일', true] :
      key === '현 부서 시작일' ? ['입사일', false] :
      key === '입학일' ? ['졸업일', true] : ['입학일', false];
    const otherRow = labels.indexOf(pair[0]) + 1;
    if (otherRow) {
      const other = calendarIso_(sheet.getRange(otherRow, target.col).getValue(), zone);
      if (other && (pair[1] ? iso > other : iso < other)) {
        throw new Error('시작일은 종료일·배치일보다 늦을 수 없습니다. ' + pair[0] + '도 확인하세요.');
      }
    }
    cell.setValue(Utilities.parseDate(iso, zone, 'yyyy-MM-dd')).setNumberFormat('yyyy-mm-dd');
    SpreadsheetApp.flush();
    cache.remove('gp-calendar:' + String(token));
    return {cell: cell.getA1Notation(), date: iso};
  } finally {
    lock.releaseLock();
  }
}
