// 2.7 — el certificado deriva del dictamen firmado; sello honesto (FIRMA
// DIGITAL · INSPECTOR, sin siglas de HW); sin PDF se declara, no se finge.
import type { MobileDictamenOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";

import { DictamenCertificate } from "./DictamenCertificate";
import { certificateView } from "./dictamenView";

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
});
