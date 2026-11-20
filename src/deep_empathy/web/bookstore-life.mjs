/** Deterministic interruption policy: spoken online replies do not move a body. */
export function interruption({brewing, walking, busy, inPerson}) {
  if (!inPerson) return 'parallel';
  return brewing || walking || busy ? 'wait' : 'pause';
}
