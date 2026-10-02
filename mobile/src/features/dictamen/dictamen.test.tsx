// 2.7 — el certificado deriva del dictamen firmado; sello honesto (FIRMA
// DIGITAL · INSPECTOR, sin siglas de HW); sin PDF se declara, no se finge.
import type { MobileDictamenOut, MobileStateOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";

import { DictamenCertificate } from "./DictamenCertificate";
import { antiguedadDelCertificado, bloqueoDelInmueble, certificateView } from "./dictamenView";

function dictamen(over: Partial<MobileDictamenOut> = {}): MobileDictamenOut {
  return {
    incident_id: "i-1",
    signed: true,
    folio: "abcdef12-3456-7890-abcd-ef1234567890",
    status: "inhabit_monitor",
    signed_by: "70000000-1111-2222-3333-444444444444",
    signed_at: "2026-07-16T18:30:00Z",
    habitable: true,
    pdf_url: "https://s3/report.pdf?sig",
    ...over,
  };
}

describe("certificateView", () => {
  it("sin firma ⇒ null (no hay certificado)", () => {
    expect(certificateView(dictamen({ signed: false, folio: null }))).toBeNull();
  });

  it("firmado habitable ⇒ folio corto, sello inspector, tiene PDF", () => {
    const v = certificateView(dictamen())!;
    expect(v.title).toMatch(/REINGRESO APROBADO/);
    expect(v.habitable).toBe(true);
    expect(v.folio).toBe("ABCDEF12");
    expect(v.seal).toBe("FIRMA DIGITAL · INSPECTOR");
    expect(v.hasPdf).toBe(true);
    // §2.1-B: jamás siglas de hardware inexistente
    expect(v.seal).not.toMatch(/HSM|TPM/);
  });

  // [T-9.33 · D-43] El sello sale del `signature_kind`, nunca de `signed_by`: un
  // VERDE que emitió el sistema no puede llevar «FIRMA DIGITAL · INSPECTOR».
  it("el sello sale del signature_kind (sistema, confirmación, inspector)", () => {
    const sistema = certificateView(
      dictamen({ signature_kind: "system" } as Partial<MobileDictamenOut>),
    )!;
    expect(sistema.seal).toBe("EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA");
    // Ni el identificador interno del firmante del sistema.
    expect(sistema.signer).toBe("SISTEMA");
    expect(
      certificateView(dictamen({ signature_kind: "confirmation" } as Partial<MobileDictamenOut>))!
        .seal,
    ).toBe("CONFIRMADO POR PERSONAL AUTORIZADO");
    expect(
      certificateView(dictamen({ signature_kind: "inspector" } as Partial<MobileDictamenOut>))!
        .seal,
    ).toBe("FIRMA DIGITAL · INSPECTOR");
  });

  // [F3·r3] La API ya publica tipo, banda y rol: el certificado los usa y NUNCA
  // imprime el identificador interno de quien firmó (ni el prefijo del UUID).
  it("nunca un UUID: el firmante sale del tipo y del rol", () => {
    const insp = certificateView(dictamen({ signature_kind: "inspector" }))!;
    expect(insp.signer).toBe("INSPECTOR");
    expect(insp.signer).not.toMatch(/70000000/);
    const hist = certificateView(dictamen({ signature_kind: null }))!;
    expect(hist.signer).toBe("INSPECTOR");
    const conf = certificateView(
      dictamen({ signature_kind: "confirmation", confirmed_by_role: "brigadista" }),
    )!;
    expect(conf.seal).toBe("CONFIRMADO POR BRIGADISTA");
    expect(conf.signer).toBe("BRIGADISTA");
    const sis = certificateView(
      dictamen({ signature_kind: "system", band: "verde", signed_by: null }),
    )!;
    expect(sis.seal).toBe("EMITIDO POR EL SISTEMA · REGLA AUTOMÁTICA · BANDA VERDE");
    expect(sis.signer).toBe("SISTEMA");
  });

  it("la banda se rotula en el certificado; sin banda (histórico) no se inventa", () => {
    expect(certificateView(dictamen({ band: "amarillo" }))!.band).toBe("AMARILLO");
    expect(certificateView(dictamen({ band: null }))!.band).toBeNull();
    expect(certificateView(dictamen({ band: "morado" }))!.band).toBeNull();
  });

  it("no habitable ⇒ habitable=false", () => {
    expect(certificateView(dictamen({ status: "restricted", habitable: false }))!.habitable).toBe(
      false,
    );
  });
});

describe("DictamenCertificate (2.7)", () => {
  const CB = { onDownloadPdf: jest.fn(), onOpenPdf: jest.fn() };

  it("con PDF sin cachear ⇒ botón DESCARGAR", async () => {
    const v = await render(
      <DictamenCertificate
        {...CB}
        cert={certificateView(dictamen())!}
        downloading={false}
        pdfCached={false}
      />,
    );
    expect(v.getByTestId("certificate")).toHaveTextContent(/FIRMA DIGITAL · INSPECTOR/);
    await fireEvent.press(v.getByTestId("download-pdf"));
    expect(CB.onDownloadPdf).toHaveBeenCalled();
  });

  it("PDF cacheado ⇒ ABRIR · DISPONIBLE OFFLINE", async () => {
    const v = await render(
      <DictamenCertificate {...CB} cert={certificateView(dictamen())!} downloading={false} pdfCached />,
    );
    expect(v.getByTestId("open-pdf")).toHaveTextContent(/DISPONIBLE OFFLINE/);
  });

  it("sin PDF ⇒ declara que el reingreso ya está autorizado (no finge PDF)", async () => {
    const v = await render(
      <DictamenCertificate
        {...CB}
        cert={certificateView(dictamen({ pdf_url: null }))!}
        downloading={false}
        pdfCached={false}
      />,
    );
    expect(v.getByTestId("no-pdf")).toHaveTextContent(/reingreso ya está autorizado/);
  });

  it("sin PDF y NO habitable ⇒ no afirma ninguna autorización", async () => {
    const v = await render(
      <DictamenCertificate
        {...CB}
        cert={
          certificateView(
            dictamen({ pdf_url: null, status: "no_inhabit_inspect", habitable: false }),
          )!
        }
        downloading={false}
        pdfCached={false}
      />,
    );
    expect(v.getByTestId("no-pdf")).not.toHaveTextContent(/autoriza/);
  });

  // [T-9.33 · D-49] Lo que se vio en el Pixel el 2026-09-30: el panel decía «NO
  // HABITAR» y el certificado, en grande, «REINGRESO APROBADO». La persona lee la
  // grande.
  it("con el inmueble BLOQUEADO, lo grande es el bloqueo y el veredicto pasa a ser un dato", async () => {
    const bloqueo = bloqueoDelInmueble(dictamen(), estado("no_habitable", "i-viejo"))!;
    const v = await render(
      <DictamenCertificate
        {...CB}
        bloqueo={bloqueo}
        cert={certificateView(dictamen({ pdf_url: null }))!}
        downloading={false}
        pdfCached={false}
      />,
    );
    expect(v.getByTestId("certificado-bloqueo")).toHaveTextContent(/REINGRESO NO AUTORIZADO/);
    expect(v.getByTestId("certificado-bloqueo")).toHaveTextContent(/OTRO evento/);
    expect(v.getByTestId("certificate")).toHaveTextContent(
      /ESTE DICTAMEN.*REINGRESO APROBADO · BAJO MONITOREO/,
    );
    // El veredicto sale UNA vez, como dato; el título grande es el del bloqueo.
    expect(v.getAllByText("REINGRESO APROBADO · BAJO MONITOREO")).toHaveLength(1);
    expect(v.getByTestId("certificado-bloqueo")).not.toHaveTextContent(/APROBADO/);
    expect(v.getByTestId("no-pdf")).not.toHaveTextContent(/autoriza/);
  });
});

function estado(
  reason: NonNullable<MobileStateOut["reentry"]["reason"]> | null,
  incidentId: string | null,
  phase: MobileStateOut["phase"] = reason === null ? "reentry_approved" : "reentry_blocked",
): Pick<MobileStateOut, "phase" | "reentry"> {
  return {
    phase,
    reentry: {
      blocked: phase !== "reentry_approved",
      dictamen_signed: true,
      dictamen_status: null,
      incident_id: incidentId,
      reason,
    },
  };
}

describe("bloqueoDelInmueble (T-9.33 · D-49)", () => {
  it("sin estado del inmueble, o con el reingreso autorizado, no hay aviso", () => {
    expect(bloqueoDelInmueble(dictamen(), undefined)).toBeNull();
    expect(bloqueoDelInmueble(dictamen(), estado(null, "i-1"))).toBeNull();
  });

  it("un dictamen habitable con el inmueble bloqueado por OTRO evento avisa, y lo dice", () => {
    const b = bloqueoDelInmueble(dictamen(), estado("no_habitable", "i-viejo"))!;
    expect(b.tono).toBe("crit");
    expect(b.titulo).toBe("REINGRESO NO AUTORIZADO");
    expect(b.deOtroEvento).toBe(true);
    expect(b.detalle).toMatch(/OTRO evento/);
  });

  it("un habitable bloqueado por SU PROPIO incidente (sin la calma) también avisa", () => {
    const b = bloqueoDelInmueble(dictamen(), estado(null, "i-1", "alert_active"))!;
    expect(b.deOtroEvento).toBe(false);
    expect(b.detalle).not.toMatch(/OTRO evento/);
  });

  it("un NO HABITAR de su propio incidente no necesita aviso: el certificado ya lo dice", () => {
    const d = dictamen({ status: "no_inhabit_inspect", habitable: false });
    expect(bloqueoDelInmueble(d, estado("no_habitable", "i-1"))).toBeNull();
  });

  it("un pendiente de OTRO evento es ámbar, no rojo", () => {
    const b = bloqueoDelInmueble(dictamen(), estado("pendiente_confirmacion", "i-otro"))!;
    expect(b.tono).toBe("warn");
  });

  // Lo que midió la revisión: el detalle de INICIO habla del INMUEBLE («aún no hay un
  // dictamen técnico firmado»), y al lado de un certificado firmado se desmiente.
  it("una escalada al inspector sobre ESTE evento no dice que falta el dictamen firmado", () => {
    const b = bloqueoDelInmueble(dictamen(), estado("pendiente_dictamen", "i-1"))!;
    expect(b.deOtroEvento).toBe(false);
    expect(b.detalle).not.toMatch(/aún no hay un dictamen/);
    expect(b.detalle).toMatch(/inspector/);
  });

  it("sin motivo (p. ej. sin la calma) no culpa a OTRO evento aunque el id sea otro", () => {
    const b = bloqueoDelInmueble(dictamen(), estado(null, "i-otro", "reentry_blocked"))!;
    expect(b.deOtroEvento).toBe(false);
    expect(b.detalle).not.toMatch(/OTRO evento/);
  });

  // Visto en el Pixel el 2026-10-01: el detalle de INICIO va tras un guion
  // («REINGRESO BLOQUEADO — consulte…») y en el certificado es una frase suelta.
  it("el detalle del certificado es una frase: empieza en mayúscula también sin motivo", () => {
    for (const e of [estado(null, "i-1", "alert_active"), estado("no_habitable", "i-otro")]) {
      expect(bloqueoDelInmueble(dictamen(), e)!.detalle).toMatch(/^[A-ZÁÉÍÓÚÑ]/);
    }
  });

  it("cada motivo del servidor tiene su detalle, distinto para este evento y para otro", () => {
    for (const motivo of ["no_habitable", "pendiente_dictamen", "pendiente_confirmacion"] as const) {
      const otro = bloqueoDelInmueble(dictamen(), estado(motivo, "i-otro"))!;
      const propio = bloqueoDelInmueble(dictamen(), estado(motivo, "i-1"))!;
      expect(otro.detalle).toMatch(/OTRO evento/);
      expect(propio.detalle).not.toMatch(/OTRO evento/);
    }
  });
});

describe("antiguedadDelCertificado", () => {
  it("el marco declara el MÁS VIEJO de los dos datos: el dictamen y el estado del inmueble", () => {
    expect(antiguedadDelCertificado(null, null)).toBeNull();
    expect(antiguedadDelCertificado(1_000, null)).toBe(1_000);
    expect(antiguedadDelCertificado(null, 2_000)).toBe(2_000);
    expect(antiguedadDelCertificado(3_000, 2_000)).toBe(2_000);
  });
});
