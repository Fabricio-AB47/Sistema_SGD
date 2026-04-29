from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Crea la tabla dbo.notificacion e indices si no existen."

    def handle(self, *args, **options):
        statements = [
            """
            IF OBJECT_ID(N'[dbo].[notificacion]', N'U') IS NULL
            BEGIN
                CREATE TABLE [dbo].[notificacion](
                    [id_notificacion] [int] IDENTITY(1,1) NOT NULL,
                    [id_user] [int] NOT NULL,
                    [actor_id] [int] NULL,
                    [titulo] [varchar](160) NOT NULL,
                    [mensaje] [varchar](800) NOT NULL,
                    [tipo] [varchar](40) NOT NULL
                        CONSTRAINT [DF_notificacion_tipo] DEFAULT ('INFO'),
                    [modulo] [varchar](80) NULL,
                    [referencia_tipo] [varchar](80) NULL,
                    [referencia_id] [int] NULL,
                    [url] [varchar](500) NULL,
                    [leida] [bit] NOT NULL
                        CONSTRAINT [DF_notificacion_leida] DEFAULT ((0)),
                    [fecha_creacion] [datetime2](0) NOT NULL
                        CONSTRAINT [DF_notificacion_fecha_creacion] DEFAULT (getdate()),
                    [fecha_lectura] [datetime2](0) NULL,
                    CONSTRAINT [PK_notificacion] PRIMARY KEY CLUSTERED ([id_notificacion] ASC)
                );
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'ix_notif_user_leida_fecha'
                  AND object_id = OBJECT_ID(N'[dbo].[notificacion]')
            )
            BEGIN
                CREATE NONCLUSTERED INDEX [ix_notif_user_leida_fecha]
                ON [dbo].[notificacion] ([id_user] ASC, [leida] ASC, [fecha_creacion] DESC);
            END
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'ix_notif_referencia'
                  AND object_id = OBJECT_ID(N'[dbo].[notificacion]')
            )
            BEGIN
                CREATE NONCLUSTERED INDEX [ix_notif_referencia]
                ON [dbo].[notificacion] ([referencia_tipo] ASC, [referencia_id] ASC);
            END
            """,
        ]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS("Tabla de notificaciones verificada correctamente."))
