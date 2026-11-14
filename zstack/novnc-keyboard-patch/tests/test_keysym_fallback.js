// 补丁 1 行为测试：keysym 回退推导（IME 场景下 event.key 为多字符）
// 被测代码直接取自 snippets/p1_after.txt（与部署到服务器的内容一致）
const fs = require('fs');
const path = require('path');

const snippet = fs.readFileSync(path.join(__dirname, '..', 'snippets', 'p1_after.txt'), 'utf8').trim();
const fn = new Function('e', 't', 't1', snippet);
const t1 = { lookup: c => c };   // 可打印 ASCII 的 keysym 即字符码

let pass = 0, fail = 0;
function check(name, got, want) {
  const ok = got === want;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name.padEnd(26)} keysym=0x${(got || 0).toString(16)} 期望=0x${want.toString(16)}`);
  ok ? pass++ : fail++;
}

// IME 激活：key 为 "Process"，须靠 code + shiftKey 推导
const ime = [
  ['Shift+2 -> @', { code: 'Digit2', shiftKey: true }, '@'],
  ['Shift+3 -> #', { code: 'Digit3', shiftKey: true }, '#'],
  ['Shift+4 -> $', { code: 'Digit4', shiftKey: true }, '$'],
  ['Shift+/ -> ?', { code: 'Slash', shiftKey: true }, '?'],
  ['Shift+; -> :', { code: 'Semicolon', shiftKey: true }, ':'],
  ["Shift+' -> \"", { code: 'Quote', shiftKey: true }, '"'],
  ['无Shift的2 -> 2', { code: 'Digit2', shiftKey: false }, '2'],
  ['无Shift的/ -> /', { code: 'Slash', shiftKey: false }, '/'],
];
console.log('  -- IME 回退路径 --');
for (const [name, ev, want] of ime) check(name, fn('Process', ev, t1), want.charCodeAt(0));

// 非 IME 正常路径：key 为单字符，走原逻辑，不得回归
console.log('  -- 单字符正常路径（不得回归）--');
for (const [k, want] of [['@', 0x40], ['#', 0x23], ['a', 0x61]]) {
  check(`单字符 key="${k}"`, fn(k, { code: 'X', shiftKey: true }, t1), want);
}

console.log(`\n  合计: PASS=${pass} FAIL=${fail}`);
process.exit(fail === 0 ? 0 : 1);
