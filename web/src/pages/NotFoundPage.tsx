import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <h1 className="soc-screen__title">404</h1>
        <p className="soc-screen__sub">La ruta no existe.</p>
        <Link className="soc-btn soc-btn--secondary" to="/">
          IR AL INICIO
        </Link>
      </div>
    </div>
  );
}
