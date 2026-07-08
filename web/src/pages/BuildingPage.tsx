import { useParams } from "react-router";

/** Dashboard por edificio. El scope fino por sitio lo impone el backend (403);
 * T-1.26 solo gatea la ruta por rol. */
export default function BuildingPage() {
  const { siteId } = useParams<"siteId">();
  return (
    <section className="soc-placeholder">
      <h1>DASHBOARD EDIFICIO</h1>
      <p className="soc-mono">{siteId}</p>
      <p className="soc-screen__sub">EN CONSTRUCCIÓN · Bloque D</p>
    </section>
  );
}
