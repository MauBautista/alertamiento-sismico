/** Pantalla en construcción: el port completo de cada mockup es T-1.27→T-1.30. */
export default function PlaceholderPage({ title, taskRef }: { title: string; taskRef: string }) {
  return (
    <section className="soc-placeholder">
      <h1>{title}</h1>
      <p className="soc-screen__sub">EN CONSTRUCCIÓN · {taskRef}</p>
    </section>
  );
}
