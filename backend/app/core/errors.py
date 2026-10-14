"""Erros de domínio convertidos em respostas HTTP claras."""


class ErroDominio(Exception):
    status = 400

    def __init__(self, mensagem: str, detalhes=None, codigo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes
        self.codigo = codigo or self.__class__.__name__


class NaoEncontrado(ErroDominio):
    status = 404


class ConflitoValidacao(ErroDominio):
    """Operação bloqueada por restrição obrigatória. `detalhes` traz as
    ocorrências e as alternativas sugeridas."""
    status = 409


class ConflitoConcorrencia(ErroDominio):
    """Outro usuário alterou o registro / reservou o recurso antes."""
    status = 409


class AcessoNegado(ErroDominio):
    status = 403


class EntradaInvalida(ErroDominio):
    status = 422
