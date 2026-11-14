// 补丁 2 行为测试：Shift 字符应发出完整修饰键序列
// 被测代码直接取自 snippets/p2_after.txt（与部署到服务器的内容一致）
const fs = require('fs');
const path = require('path');

let p2 = fs.readFileSync(path.join(__dirname, '..', 'snippets', 'p2_after.txt'), 'utf8').trim();
p2 = p2.replace(/\}_handleKeyUp\(t\)\{$/, '');   // 去掉尾部方法分隔符，仅保留三元表达式
p2 = p2.replace(/t\$/g, 'KS');                   // 规避 $ 标识符，便于注入作用域

const KS = { A: { XK_Shift_L: 0xffe1 } };
const fn = new Function('i', 'e', 't', 'KS', p2);

function run(keysym, code, shiftKey) {
  const log = [];
  const ctx = {
    _sendKeyEvent: (ks, cd, down) =>
      log.push(`${down ? 'down' : 'up  '} ${ks === 0xffe1 ? 'Shift_L' : 'keysym'}=0x${(ks || 0).toString(16)} (${cd})`),
  };
  fn.call(ctx, keysym, code, { shiftKey }, KS);
  return log;
}

let pass = 0, fail = 0;
function check(name, cond, extra) {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`);
  cond ? pass++ : fail++;
}

const r1 = run(0x40, 'Digit2', true);
check('Shift+2(@) 发出完整序列', r1.length === 4, `事件数=${r1.length} 期望=4`);
r1.forEach(l => console.log(`         ${l}`));
check('序列首尾均为 Shift_L', r1.length === 4 && r1[0].includes('Shift_L') && r1[3].includes('Shift_L'));

const r2 = run(0x41, 'KeyA', true);
check('Shift+A 保持原行为', r2.length === 1, `事件数=${r2.length} 期望=1`);

const r3 = run(0x32, 'Digit2', false);
check('无 Shift 的 2 保持原行为', r3.length === 1, `事件数=${r3.length} 期望=1`);

const r4 = run(0xffe1, 'ShiftLeft', true);
check('Shift 键自身不递归触发', r4.length === 1, `事件数=${r4.length} 期望=1`);

console.log(`\n  合计: PASS=${pass} FAIL=${fail}`);
process.exit(fail === 0 ? 0 : 1);
