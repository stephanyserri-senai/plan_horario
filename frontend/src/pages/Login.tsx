import { useState } from "react";
import { supabase } from "../auth";
import { useApp } from "../contexto";

export default function Login() {
  const { entrar, auth, erroAcesso, recuperarSenha, sair } = useApp();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [info, setInfo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const modoSupabase = auth?.modo === "supabase";
  return (
    <div className="login">
      <form onSubmit={async (e) => {
        e.preventDefault();
        setErro(""); setInfo("");
        setEnviando(true);
        try { await entrar(email.trim(), senha); } catch (x: any) { setErro(x.message); } finally { setEnviando(false); }
      }}>
        <img className="login-icone" src="/icone.png" alt="" width={84} height={84} />
        <h1>Planejamento Acadêmico</h1>
        <p className="sub">Horários, capacidade institucional e simulação de ofertas</p>
        {erroAcesso && <div className="erro-box" role="alert">{erroAcesso}{modoSupabase && <> <button type="button" className="btn-link" onClick={sair}>Sair</button></>}</div>}
        <label className="campo"><span className="campo-rotulo">{modoSupabase ? "E-mail" : "E-mail ou usuário"}</span>
          <input type={modoSupabase ? "email" : "text"} autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="campo"><span className="campo-rotulo">Senha</span>
          <input type="password" autoComplete="current-password" required value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        {erro && <div className="erro-box" role="alert">{erro}</div>}
        {info && <p className="aviso-inline" role="status">{info}</p>}
        <button className="btn btn-primario" disabled={enviando}>{enviando ? "Entrando…" : "Entrar"}</button>
        {modoSupabase && <button type="button" className="btn-link" onClick={async () => {
          setErro(""); setInfo("");
          if (!email) { setErro("Informe o e-mail para receber o link de redefinição."); return; }
          try { await recuperarSenha(email.trim()); setInfo("Se o e-mail estiver cadastrado, você receberá um link para definir uma nova senha."); }
          catch (x: any) { setErro(x.message); }
        }}>Esqueci minha senha</button>}
      </form>
    </div>
  );
}

export function DefinirSenha() {
  const { concluirDefinicaoSenha } = useApp();
  const [senha, setSenha] = useState("");
  const [conf, setConf] = useState("");
  const [erro, setErro] = useState("");
  return (
    <div className="login">
      <form onSubmit={async (e) => {
        e.preventDefault();
        setErro("");
        if (senha.length < 8) return setErro("A senha deve ter ao menos 8 caracteres.");
        if (senha !== conf) return setErro("As senhas não conferem.");
        const { error } = await supabase()!.auth.updateUser({ password: senha });
        if (error) return setErro(error.message);
        await concluirDefinicaoSenha();
      }}>
        <img className="login-icone" src="/icone.png" alt="" width={84} height={84} />
        <h1>Definir senha</h1>
        <p className="sub">Crie a senha de acesso à plataforma.</p>
        <label className="campo"><span className="campo-rotulo">Nova senha</span><input type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        <label className="campo"><span className="campo-rotulo">Confirmar senha</span><input type="password" autoComplete="new-password" value={conf} onChange={(e) => setConf(e.target.value)} /></label>
        {erro && <div className="erro-box" role="alert">{erro}</div>}
        <button className="btn btn-primario">Salvar senha</button>
      </form>
    </div>
  );
}
