from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Crea la tabla dbo.seguimiento_alerta_evaluacion e indices si no existen."

    def handle(self, *args, **options):
        statements = [
            """
            IF OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]', N'U') IS NULL
            BEGIN
                CREATE TABLE [dbo].[seguimiento_alerta_evaluacion](
                    [id_alerta] [int] IDENTITY(1,1) NOT NULL,
                    [referencia_tipo] [varchar](80) NOT NULL,
                    [referencia_id] [int] NOT NULL,
                    [id_user] [int] NOT NULL,
                    [correo] [varchar](254) NOT NULL,
                    [asunto] [varchar](200) NOT NULL,
                    [plantilla] [varchar](100) NOT NULL,
                    [contexto_json] [nvarchar](max) NULL,
                    [numero_envios] [int] NOT NULL
                        CONSTRAINT [DF_seg_alerta_numero_envios] DEFAULT ((0)),
                    [max_envios] [int] NOT NULL
                        CONSTRAINT [DF_seg_alerta_max_envios] DEFAULT ((4)),
                    [intervalo_dias] [int] NOT NULL
                        CONSTRAINT [DF_seg_alerta_intervalo] DEFAULT ((2)),
                    [activa] [bit] NOT NULL
                        CONSTRAINT [DF_seg_alerta_activa] DEFAULT ((1)),
                    [fecha_inicio] [datetime2](0) NOT NULL
                        CONSTRAINT [DF_seg_alerta_inicio] DEFAULT (getdate()),
                    [fecha_ultimo_envio] [datetime2](0) NULL,
                    [proximo_envio] [datetime2](0) NULL,
                    [fecha_cierre] [datetime2](0) NULL,
                    [motivo_cierre] [varchar](200) NULL,
                    [ultimo_error] [varchar](1000) NULL,
                    CONSTRAINT [PK_seguimiento_alerta_evaluacion]
                        PRIMARY KEY CLUSTERED ([id_alerta] ASC),
                    CONSTRAINT [CK_seg_alerta_envios]
                        CHECK ([numero_envios] >= (0) AND [max_envios] >= [numero_envios]),
                    CONSTRAINT [CK_seg_alerta_intervalo]
                        CHECK ([intervalo_dias] > (0))
                );
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'uq_seguimiento_alerta_eval'
                  AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]')
            )
            BEGIN
                CREATE UNIQUE NONCLUSTERED INDEX [uq_seguimiento_alerta_eval]
                ON [dbo].[seguimiento_alerta_evaluacion]
                ([referencia_tipo] ASC, [referencia_id] ASC, [id_user] ASC, [plantilla] ASC);
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'ix_seg_alerta_activa_prox'
                  AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]')
            )
            BEGIN
                CREATE NONCLUSTERED INDEX [ix_seg_alerta_activa_prox]
                ON [dbo].[seguimiento_alerta_evaluacion] ([activa] ASC, [proximo_envio] ASC);
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'ix_seg_alerta_referencia'
                  AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]')
            )
            BEGIN
                CREATE NONCLUSTERED INDEX [ix_seg_alerta_referencia]
                ON [dbo].[seguimiento_alerta_evaluacion] ([referencia_tipo] ASC, [referencia_id] ASC);
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.foreign_keys
                WHERE name = N'FK_seg_alerta_usuario'
                  AND parent_object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]')
            )
            BEGIN
                ALTER TABLE [dbo].[seguimiento_alerta_evaluacion] WITH CHECK ADD
                    CONSTRAINT [FK_seg_alerta_usuario]
                    FOREIGN KEY([id_user]) REFERENCES [dbo].[usuario] ([id_user]);
            END
            """,
        ]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS("Tabla de alertas de evaluacion verificada correctamente."))
