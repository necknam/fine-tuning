const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname,'Code.gs'),'utf8');
function fixture(){
  const values=new Map([['18,4',new Date('2020-02-29T00:00:00Z')],['19,4',new Date('2026-01-01T00:00:00Z')]]);
  const labels={18:'입사일 ★',19:'현 부서 시작일 ★',34:'입학일',35:'졸업일'};
  const target={row:18,col:4,key:'입사일',baseline:'2020-02-29',sheetId:794346946};
  let cached=JSON.stringify(target),released=0;
  const sheet={getSheetId:()=>794346946,getLastRow:()=>35,getRange:(row,col)=>({
    getDisplayValue:()=>labels[row]||'',getValue:()=>values.get(row+','+col)||'',getFormula:()=>'',
    getDisplayValues:()=>Array.from({length:35},(_,i)=>[labels[i+1]||'']),
    setValue(value){values.set(row+','+col,value);return this;},setNumberFormat(){return this;},getA1Notation:()=>String.fromCharCode(64+col)+row
  })};
  const ss={getId:()=>'1Rt2zvnjizTrMyI4RPdBcMrO6mR_EnbdMahnXjRKdabw',getSheetById:()=>sheet,getSpreadsheetTimeZone:()=>'UTC'};
  const context=vm.createContext({Date,console,Utilities:{formatDate:d=>d.toISOString().slice(0,10),parseDate:s=>new Date(s+'T00:00:00Z')},
    SpreadsheetApp:{getActiveSpreadsheet:()=>ss,flush(){}},CacheService:{getUserCache:()=>({get:()=>cached,remove:()=>{cached=null;}})},
    LockService:{getDocumentLock:()=>({waitLock(){},releaseLock(){released++;}})}});
  vm.runInContext(code,context);
  return{context,values,labels,target,setCache:x=>{cached=x;},released:()=>released};
}
let f=fixture();
assert.equal(f.context.calendarParts_('2020-02-29').day,29);
for(const iso of ['2023-02-29','2020-02-30','2020-13-01','2020-01-00','1899-12-31','2020-2-1'])
  assert.throws(()=>f.context.calendarParts_(iso));
assert.equal(f.context.calendarLabel_('입사일 ★'),'입사일');
assert.equal(f.context.saveCalendarDate('token','2021-03-02').date,'2021-03-02');
assert.equal(f.values.get('18,4').toISOString().slice(0,10),'2021-03-02');
assert.equal(f.released(),1);
assert.throws(()=>f.context.saveCalendarDate('token','2021-03-02'),/유효시간/);
f=fixture();assert.throws(()=>f.context.saveCalendarDate('token','2026-02-01'),/시작일/);assert.equal(f.released(),1);
f=fixture();f.values.set('18,4',new Date('2021-01-01T00:00:00Z'));
assert.throws(()=>f.context.saveCalendarDate('token','2022-01-01'),/다른 사용자/);
f=fixture();f.labels[18]='다른 항목';assert.throws(()=>f.context.saveCalendarDate('token','2022-01-01'),/입력 위치/);
f=fixture();f.target.col=9;f.setCache(JSON.stringify(f.target));assert.throws(()=>f.context.saveCalendarDate('token','2022-01-01'),/입력 위치/);
f=fixture();f.values.set('18,4','원문');assert.throws(()=>f.context.saveCalendarDate('token','2022-01-01'),/날짜가 아닌/);
console.log('Calendar checks passed: leap dates, bounds, save, expiry, chronology, concurrent edit, target scope.');
