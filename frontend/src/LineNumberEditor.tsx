import { useLayoutEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'

interface Props {
  value: string
  onChange: (value: string) => void
  label: string
  rows?: number
  disabled?: boolean
  readOnly?: boolean
}

export default function LineNumberEditor({
  value,
  onChange,
  label,
  rows = 24,
  disabled = false,
  readOnly = false,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const numbersRef = useRef<HTMLDivElement>(null)
  const lineCount = value.split(/\r\n|\r|\n/).length
  const lineNumbers = useMemo(
    () => Array.from({ length: lineCount }, (_, index) => index + 1).join('\n'),
    [lineCount],
  )
  const gutterWidth = Math.max(3, String(lineCount).length) + 2

  const syncScroll = () => {
    if (textareaRef.current && numbersRef.current) {
      numbersRef.current.style.transform = `translateY(-${textareaRef.current.scrollTop}px)`
    }
  }

  useLayoutEffect(syncScroll, [value])

  return (
    <div
      className={`line-number-editor${disabled ? ' line-number-editor-disabled' : ''}`}
      style={{ '--editor-gutter-width': `${gutterWidth}ch` } as CSSProperties}
    >
      <div className="line-number-editor-gutter" aria-hidden="true">
        <div ref={numbersRef}>{lineNumbers}</div>
      </div>
      <textarea
        ref={textareaRef}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onScroll={syncScroll}
        rows={rows}
        wrap="off"
        spellCheck={false}
        disabled={disabled}
        readOnly={readOnly}
      />
    </div>
  )
}
