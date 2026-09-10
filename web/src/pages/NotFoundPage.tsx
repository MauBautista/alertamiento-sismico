import { ButtonLink } from "../components/Button";

export default function NotFoundPage() {
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <h1 className="soc-screen__title">404</h1>
        <p className="soc-screen__sub">La ruta no existe.</p>
        <ButtonLink variant="secondary" to="/">
          IR AL INICIO
        </ButtonLink>
      </div>
    </div>
  );
}
