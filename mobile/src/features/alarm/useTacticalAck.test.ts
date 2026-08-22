// [T-2.147.b] La lógica del acuse: qué NO manda, y qué hace con un fallo.
import { tacticalAckIncidentsIncidentIdTacticalAckPost } from "@takab/sdk";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import { useTacticalAck } from "./useTacticalAck";

jest.mock("@takab/sdk", () => ({
  tacticalAckIncidentsIncidentIdTacticalAckPost: jest.fn(),
}));

const post = tacticalAckIncidentsIncidentIdTacticalAckPost as jest.Mock;

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: { already: false }, error: undefined });
});

it("sin incidente NO llama al backend", async () => {
  const { result } = await renderHook(() => useTacticalAck(null));
  await act(async () => {
    await result.current.acusar();
  });
  expect(post).not.toHaveBeenCalled();
  expect(result.current.estado).toBe("idle");
});

it("acusa una vez y queda en estado terminal", async () => {
  const { result } = await renderHook(() => useTacticalAck("inc-1"));
  await act(async () => {
    await result.current.acusar();
  });
  await waitFor(() => expect(result.current.estado).toBe("acusado"));
  expect(post).toHaveBeenCalledWith({ path: { incident_id: "inc-1" } });
  expect(result.current.acusadoEn).not.toBeNull();

  // Ya acusado: no se vuelve a mandar. El endpoint es idempotente por persona, así
  // que un segundo envío no rompería nada — pero mandar sin necesidad desde el
  // camino de emergencia es ruido que alguien acaba teniendo que explicar.
  await act(async () => {
    await result.current.acusar();
  });
  expect(post).toHaveBeenCalledTimes(1);
});

it("un rechazo del backend se DECLARA y deja reintentar", async () => {
  post.mockResolvedValueOnce({ data: undefined, error: { detail: "nope" } });
  const { result } = await renderHook(() => useTacticalAck("inc-1"));
  await act(async () => {
    await result.current.acusar();
  });
  await waitFor(() => expect(result.current.estado).toBe("error"));
  expect(result.current.acusadoEn).toBeNull();

  // Y desde `error` sí se puede reintentar: es el punto entero de declararlo.
  post.mockResolvedValueOnce({ data: { already: true }, error: undefined });
  await act(async () => {
    await result.current.acusar();
  });
  await waitFor(() => expect(result.current.estado).toBe("acusado"));
  expect(post).toHaveBeenCalledTimes(2);
});

it("una excepción de red tampoco se traga", async () => {
  post.mockRejectedValueOnce(new Error("sin red"));
  const { result } = await renderHook(() => useTacticalAck("inc-1"));
  await act(async () => {
    await result.current.acusar();
  });
  await waitFor(() => expect(result.current.estado).toBe("error"));
});
