import { useState } from "react";
import { useApp } from "../contexto";

export default function Login() {
  const { entrar } = useApp();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  return (
    <div className="login">
      <form onSubmit={async (e) => {
        e.preventDefault();
        setErro("");
        setEnviando(true);
        try { await entrar(email, senha); } catch (x: any) { setErro(x.message); } finally { setEnviando(false); }
      }}>
        <h1>Planejamento Acadêmico</h1>
        <p className="sub">Horários, capacidade institucional e simulação de ofertas</p>
        <label className="campo"><span className="campo-rotulo">E-mail</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="campo"><span className="campo-rotulo">Senha</span>
          <input type="password" autoComplete="current-password" required value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        {erro && <div className="erro-box" role="alert">{erro}</div>}
        <button className="btn btn-primario" disabled={enviando}>{enviando ? "Entrando…" : "Entrar"}</button>
      </form>
    </div>
  );
}
