// App icon artwork, rendered to PNG by next/og (inline styles only).
export function StrideMark({ size }: { size: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#111111",
        color: "#ffffff",
        fontSize: size * 0.62,
        fontWeight: 800,
        letterSpacing: -size * 0.02,
      }}
    >
      S
    </div>
  );
}
