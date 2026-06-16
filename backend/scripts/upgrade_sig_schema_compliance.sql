USE [$(DBName)]
GO

SET XACT_ABORT ON
GO

/* =========================================================
   SIG schema complement
   Run this over the existing SIG database. It is idempotent:
   every structural change checks whether the object already exists.
   ========================================================= */

/* ---------- Model alignment columns ---------- */
IF COL_LENGTH('dbo.criterio', 'ponderacion') IS NULL
    ALTER TABLE [dbo].[criterio] ADD [ponderacion] [decimal](5, 2) NULL;
GO

IF COL_LENGTH('dbo.subcriterio', 'ponderacion') IS NULL
    ALTER TABLE [dbo].[subcriterio] ADD [ponderacion] [decimal](5, 2) NULL;
GO

IF COL_LENGTH('dbo.elemento_fundamental', 'tipo_elemento') IS NULL
    ALTER TABLE [dbo].[elemento_fundamental]
        ADD [tipo_elemento] [varchar](20) NOT NULL
            CONSTRAINT [df_elemento_fundamental_tipo] DEFAULT ('ESENCIAL');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'ck_elemento_fundamental_tipo'
      AND parent_object_id = OBJECT_ID(N'[dbo].[elemento_fundamental]')
)
BEGIN
    ALTER TABLE [dbo].[elemento_fundamental] WITH CHECK ADD
        CONSTRAINT [ck_elemento_fundamental_tipo]
        CHECK ([tipo_elemento] IN ('ESENCIAL', 'COMPLEMENTARIO'));
END
GO

IF OBJECT_ID(N'[dbo].[clasificacion_elemento_fundamental]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[clasificacion_elemento_fundamental](
        [id_clasificacion] [int] IDENTITY(1,1) NOT NULL,
        [codigo] [varchar](20) NOT NULL,
        [nombre] [varchar](100) NOT NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_clasificacion_ef_activo] DEFAULT ((1)),
        CONSTRAINT [pk_clasificacion_ef] PRIMARY KEY CLUSTERED ([id_clasificacion] ASC),
        CONSTRAINT [uq_clasificacion_ef_codigo] UNIQUE NONCLUSTERED ([codigo] ASC)
    );
END
GO

IF COL_LENGTH('dbo.elemento_fundamental', 'id_clasificacion') IS NULL
    ALTER TABLE [dbo].[elemento_fundamental] ADD [id_clasificacion] [int] NULL;
GO

IF OBJECT_ID(N'[dbo].[clasificacion_elemento_fundamental]', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'fk_elemento_fundamental_clasificacion'
      AND parent_object_id = OBJECT_ID(N'[dbo].[elemento_fundamental]')
)
BEGIN
    ALTER TABLE [dbo].[elemento_fundamental] WITH CHECK ADD
        CONSTRAINT [fk_elemento_fundamental_clasificacion]
        FOREIGN KEY ([id_clasificacion])
        REFERENCES [dbo].[clasificacion_elemento_fundamental] ([id_clasificacion]);
END
GO

IF COL_LENGTH('dbo.ciclo_evaluacion', 'id_documento_autorizacion') IS NULL
    ALTER TABLE [dbo].[ciclo_evaluacion] ADD [id_documento_autorizacion] [int] NULL;
GO

IF COL_LENGTH('dbo.ciclo_evaluacion', 'aprobado_por') IS NULL
    ALTER TABLE [dbo].[ciclo_evaluacion] ADD [aprobado_por] [int] NULL;
GO

IF COL_LENGTH('dbo.ciclo_evaluacion', 'fecha_aprobacion') IS NULL
    ALTER TABLE [dbo].[ciclo_evaluacion] ADD [fecha_aprobacion] [datetime2](0) NULL;
GO

IF COL_LENGTH('dbo.ciclo_evaluacion', 'observacion_aprobacion') IS NULL
    ALTER TABLE [dbo].[ciclo_evaluacion] ADD [observacion_aprobacion] [varchar](1000) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'fk_ciclo_documento_autorizacion'
      AND parent_object_id = OBJECT_ID(N'[dbo].[ciclo_evaluacion]')
)
BEGIN
    ALTER TABLE [dbo].[ciclo_evaluacion] WITH CHECK ADD
        CONSTRAINT [fk_ciclo_documento_autorizacion]
        FOREIGN KEY ([id_documento_autorizacion])
        REFERENCES [dbo].[documento] ([id_documento]);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'fk_ciclo_aprobado_por'
      AND parent_object_id = OBJECT_ID(N'[dbo].[ciclo_evaluacion]')
)
BEGIN
    ALTER TABLE [dbo].[ciclo_evaluacion] WITH CHECK ADD
        CONSTRAINT [fk_ciclo_aprobado_por]
        FOREIGN KEY ([aprobado_por])
        REFERENCES [dbo].[usuario] ([id_user]);
END
GO

IF COL_LENGTH('dbo.registro_evidencia', 'enviado_revision_por') IS NULL
    ALTER TABLE [dbo].[registro_evidencia] ADD [enviado_revision_por] [int] NULL;
GO

IF COL_LENGTH('dbo.registro_evidencia', 'fecha_envio_revision') IS NULL
    ALTER TABLE [dbo].[registro_evidencia] ADD [fecha_envio_revision] [datetime2](0) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'fk_registro_evidencia_enviado_revision_por'
      AND parent_object_id = OBJECT_ID(N'[dbo].[registro_evidencia]')
)
BEGIN
    ALTER TABLE [dbo].[registro_evidencia] WITH CHECK ADD
        CONSTRAINT [fk_registro_evidencia_enviado_revision_por]
        FOREIGN KEY ([enviado_revision_por])
        REFERENCES [dbo].[usuario] ([id_user]);
END
GO

UPDATE re
SET [id_indicador] = ef.[id_indicador]
FROM [dbo].[registro_evidencia] re
JOIN [dbo].[elemento_fundamental] ef
    ON ef.[id_elemento_fundamental] = re.[id_elemento_fundamental]
WHERE re.[id_indicador] IS NULL;
GO

IF COL_LENGTH('dbo.informe_autoevaluacion', 'fecha_aprobacion') IS NULL
    ALTER TABLE [dbo].[informe_autoevaluacion] ADD [fecha_aprobacion] [datetime2](0) NULL;
GO

IF COL_LENGTH('dbo.informe_autoevaluacion', 'observacion_aprobacion') IS NULL
    ALTER TABLE [dbo].[informe_autoevaluacion] ADD [observacion_aprobacion] [varchar](1000) NULL;
GO

IF COL_LENGTH('dbo.documento', 'ruta_local') IS NOT NULL
BEGIN
    ALTER TABLE [dbo].[documento] ALTER COLUMN [ruta_local] [varchar](1000) NULL;
END
GO

IF COL_LENGTH('dbo.version_documento', 'ruta_local') IS NOT NULL
BEGIN
    ALTER TABLE [dbo].[version_documento] ALTER COLUMN [ruta_local] [varchar](1000) NULL;
END
GO

IF COL_LENGTH('dbo.documento', 'extension_archivo') IS NOT NULL
BEGIN
    ALTER TABLE [dbo].[documento] ALTER COLUMN [extension_archivo] [varchar](20) NULL;
END
GO

IF COL_LENGTH('dbo.historial_password', 'algoritmo_hash') IS NULL
    ALTER TABLE [dbo].[historial_password]
        ADD [algoritmo_hash] [varchar](30) NOT NULL
            CONSTRAINT [df_historial_password_algoritmo_col] DEFAULT ('argon2');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    JOIN sys.columns c
        ON c.object_id = dc.parent_object_id
       AND c.column_id = dc.parent_column_id
    WHERE dc.parent_object_id = OBJECT_ID(N'[dbo].[historial_password]')
      AND c.name = N'algoritmo_hash'
)
BEGIN
    ALTER TABLE [dbo].[historial_password]
        ADD CONSTRAINT [df_historial_password_algoritmo]
        DEFAULT ('argon2') FOR [algoritmo_hash];
END
GO

/* OTP values are transient. This conversion aligns the column with the
   SHA-256 hexadecimal value generated by the application. */
IF EXISTS (
    SELECT 1
    FROM sys.columns c
    JOIN sys.types t ON t.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID(N'[dbo].[usuario_otp]')
      AND c.name = N'codigo_otp_hash'
      AND t.name IN (N'varbinary', N'binary')
)
BEGIN
    DELETE FROM [dbo].[usuario_otp];
    ALTER TABLE [dbo].[usuario_otp] ALTER COLUMN [codigo_otp_hash] [char](64) NOT NULL;
END
GO

/* ---------- Operational tables missing from the final script ---------- */
IF OBJECT_ID(N'[dbo].[estado_tarea_evidencia]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[estado_tarea_evidencia](
        [id_estado_tarea] [int] IDENTITY(1,1) NOT NULL,
        [descripcion] [varchar](100) NOT NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_estado_tarea_evidencia_activo] DEFAULT ((1)),
        CONSTRAINT [pk_estado_tarea_evidencia] PRIMARY KEY CLUSTERED ([id_estado_tarea] ASC),
        CONSTRAINT [uq_estado_tarea_evidencia_descripcion] UNIQUE NONCLUSTERED ([descripcion] ASC)
    );
END
GO

IF OBJECT_ID(N'[dbo].[tarea_evidencia]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[tarea_evidencia](
        [id_tarea_evidencia] [int] IDENTITY(1,1) NOT NULL,
        [id_ciclo] [int] NOT NULL,
        [id_indicador] [int] NOT NULL,
        [id_elemento_fundamental] [int] NOT NULL,
        [id_usuario_responsable] [int] NOT NULL,
        [id_estado_tarea] [int] NOT NULL,
        [fecha_asignacion] [datetime2](0) NULL CONSTRAINT [df_tarea_evidencia_fecha] DEFAULT (sysutcdatetime()),
        [fecha_limite] [datetime2](0) NULL,
        [fecha_cierre] [datetime2](0) NULL,
        [prioridad] [varchar](20) NULL,
        [observacion] [varchar](1000) NULL,
        [resultado_tarea] [varchar](1000) NULL,
        [asignado_por] [int] NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_tarea_evidencia_activo] DEFAULT ((1)),
        CONSTRAINT [pk_tarea_evidencia] PRIMARY KEY CLUSTERED ([id_tarea_evidencia] ASC),
        CONSTRAINT [uq_tarea_evidencia_operativa]
            UNIQUE NONCLUSTERED ([id_ciclo], [id_indicador], [id_elemento_fundamental], [id_usuario_responsable], [activo]),
        CONSTRAINT [ck_tarea_evidencia_prioridad]
            CHECK ([prioridad] IS NULL OR [prioridad] IN ('BAJA', 'MEDIA', 'ALTA', 'CRITICA')),
        CONSTRAINT [ck_tarea_evidencia_fechas]
            CHECK ([fecha_cierre] IS NULL OR [fecha_asignacion] IS NULL OR [fecha_cierre] >= [fecha_asignacion])
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_ciclo')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_ciclo]
        FOREIGN KEY([id_ciclo]) REFERENCES [dbo].[ciclo_evaluacion] ([id_ciclo]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_indicador')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_indicador]
        FOREIGN KEY([id_indicador]) REFERENCES [dbo].[indicador] ([id_indicador]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_elemento')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_elemento]
        FOREIGN KEY([id_elemento_fundamental]) REFERENCES [dbo].[elemento_fundamental] ([id_elemento_fundamental]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_responsable')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_responsable]
        FOREIGN KEY([id_usuario_responsable]) REFERENCES [dbo].[usuario] ([id_user]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_estado')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_estado]
        FOREIGN KEY([id_estado_tarea]) REFERENCES [dbo].[estado_tarea_evidencia] ([id_estado_tarea]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_tarea_evidencia_asignado_por')
    ALTER TABLE [dbo].[tarea_evidencia] WITH CHECK ADD CONSTRAINT [fk_tarea_evidencia_asignado_por]
        FOREIGN KEY([asignado_por]) REFERENCES [dbo].[usuario] ([id_user]);
GO

IF OBJECT_ID(N'[dbo].[notificacion]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[notificacion](
        [id_notificacion] [int] IDENTITY(1,1) NOT NULL,
        [id_user] [int] NOT NULL,
        [actor_id] [int] NULL,
        [titulo] [varchar](160) NOT NULL,
        [mensaje] [varchar](800) NOT NULL,
        [tipo] [varchar](40) NOT NULL CONSTRAINT [df_notificacion_tipo] DEFAULT ('INFO'),
        [modulo] [varchar](80) NULL,
        [referencia_tipo] [varchar](80) NULL,
        [referencia_id] [int] NULL,
        [url] [varchar](500) NULL,
        [leida] [bit] NOT NULL CONSTRAINT [df_notificacion_leida] DEFAULT ((0)),
        [fecha_creacion] [datetime2](0) NOT NULL CONSTRAINT [df_notificacion_fecha] DEFAULT (sysutcdatetime()),
        [fecha_lectura] [datetime2](0) NULL,
        CONSTRAINT [pk_notificacion] PRIMARY KEY CLUSTERED ([id_notificacion] ASC)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_notif_user_leida_fecha' AND object_id = OBJECT_ID(N'[dbo].[notificacion]'))
    CREATE NONCLUSTERED INDEX [ix_notif_user_leida_fecha]
    ON [dbo].[notificacion] ([id_user] ASC, [leida] ASC, [fecha_creacion] DESC);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_notif_referencia' AND object_id = OBJECT_ID(N'[dbo].[notificacion]'))
    CREATE NONCLUSTERED INDEX [ix_notif_referencia]
    ON [dbo].[notificacion] ([referencia_tipo] ASC, [referencia_id] ASC);
GO

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
        [numero_envios] [int] NOT NULL CONSTRAINT [df_seg_alerta_numero_envios] DEFAULT ((0)),
        [max_envios] [int] NOT NULL CONSTRAINT [df_seg_alerta_max_envios] DEFAULT ((4)),
        [intervalo_dias] [int] NOT NULL CONSTRAINT [df_seg_alerta_intervalo] DEFAULT ((2)),
        [activa] [bit] NOT NULL CONSTRAINT [df_seg_alerta_activa] DEFAULT ((1)),
        [fecha_inicio] [datetime2](0) NOT NULL CONSTRAINT [df_seg_alerta_inicio] DEFAULT (sysutcdatetime()),
        [fecha_ultimo_envio] [datetime2](0) NULL,
        [proximo_envio] [datetime2](0) NULL,
        [fecha_cierre] [datetime2](0) NULL,
        [motivo_cierre] [varchar](200) NULL,
        [ultimo_error] [varchar](1000) NULL,
        CONSTRAINT [pk_seguimiento_alerta_evaluacion] PRIMARY KEY CLUSTERED ([id_alerta] ASC),
        CONSTRAINT [ck_seg_alerta_envios] CHECK ([numero_envios] >= (0) AND [max_envios] >= [numero_envios]),
        CONSTRAINT [ck_seg_alerta_intervalo] CHECK ([intervalo_dias] > (0))
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'uq_seguimiento_alerta_eval' AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]'))
    CREATE UNIQUE NONCLUSTERED INDEX [uq_seguimiento_alerta_eval]
    ON [dbo].[seguimiento_alerta_evaluacion] ([referencia_tipo], [referencia_id], [id_user], [plantilla]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_seg_alerta_activa_prox' AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]'))
    CREATE NONCLUSTERED INDEX [ix_seg_alerta_activa_prox]
    ON [dbo].[seguimiento_alerta_evaluacion] ([activa], [proximo_envio]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_seg_alerta_referencia' AND object_id = OBJECT_ID(N'[dbo].[seguimiento_alerta_evaluacion]'))
    CREATE NONCLUSTERED INDEX [ix_seg_alerta_referencia]
    ON [dbo].[seguimiento_alerta_evaluacion] ([referencia_tipo], [referencia_id]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_seg_alerta_usuario')
    ALTER TABLE [dbo].[seguimiento_alerta_evaluacion] WITH CHECK ADD CONSTRAINT [fk_seg_alerta_usuario]
        FOREIGN KEY([id_user]) REFERENCES [dbo].[usuario] ([id_user]);
GO

IF OBJECT_ID(N'[dbo].[seguimiento_accion_mejora]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[seguimiento_accion_mejora](
        [id_seguimiento_accion] [int] IDENTITY(1,1) NOT NULL,
        [id_accion] [int] NOT NULL,
        [fecha_seguimiento] [datetime2](0) NULL CONSTRAINT [df_seguimiento_accion_fecha] DEFAULT (sysutcdatetime()),
        [porcentaje_avance] [decimal](5, 2) NOT NULL,
        [observacion] [varchar](1000) NULL,
        [id_documento] [int] NULL,
        [registrado_por] [int] NULL,
        [semaforo] [varchar](20) NULL,
        CONSTRAINT [pk_seguimiento_accion_mejora] PRIMARY KEY CLUSTERED ([id_seguimiento_accion] ASC),
        CONSTRAINT [ck_seguimiento_accion_porcentaje] CHECK ([porcentaje_avance] >= 0 AND [porcentaje_avance] <= 100),
        CONSTRAINT [ck_seguimiento_accion_semaforo] CHECK ([semaforo] IS NULL OR [semaforo] IN ('VERDE', 'AMARILLO', 'ROJO'))
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_seguimiento_accion_accion')
    ALTER TABLE [dbo].[seguimiento_accion_mejora] WITH CHECK ADD CONSTRAINT [fk_seguimiento_accion_accion]
        FOREIGN KEY([id_accion]) REFERENCES [dbo].[accion_mejora] ([id_accion]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_seguimiento_accion_documento')
    ALTER TABLE [dbo].[seguimiento_accion_mejora] WITH CHECK ADD CONSTRAINT [fk_seguimiento_accion_documento]
        FOREIGN KEY([id_documento]) REFERENCES [dbo].[documento] ([id_documento]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_seguimiento_accion_usuario')
    ALTER TABLE [dbo].[seguimiento_accion_mejora] WITH CHECK ADD CONSTRAINT [fk_seguimiento_accion_usuario]
        FOREIGN KEY([registrado_por]) REFERENCES [dbo].[usuario] ([id_user]);
GO

IF OBJECT_ID(N'[dbo].[historial_estado_evidencia]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[historial_estado_evidencia](
        [id_historial_estado] [bigint] IDENTITY(1,1) NOT NULL,
        [id_registro] [int] NOT NULL,
        [id_estado_anterior] [int] NULL,
        [id_estado_nuevo] [int] NOT NULL,
        [id_usuario] [int] NULL,
        [tipo_evento] [varchar](50) NOT NULL CONSTRAINT [df_hist_estado_evid_tipo] DEFAULT ('CAMBIO_ESTADO'),
        [fecha_evento] [datetime2](0) NOT NULL CONSTRAINT [df_hist_estado_evid_fecha] DEFAULT (sysutcdatetime()),
        [comentario] [varchar](1000) NULL,
        CONSTRAINT [pk_historial_estado_evidencia] PRIMARY KEY CLUSTERED ([id_historial_estado] ASC)
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_hist_estado_evid_registro_fecha' AND object_id = OBJECT_ID(N'[dbo].[historial_estado_evidencia]'))
    CREATE NONCLUSTERED INDEX [ix_hist_estado_evid_registro_fecha]
    ON [dbo].[historial_estado_evidencia] ([id_registro], [fecha_evento] DESC);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_hist_estado_evid_registro')
    ALTER TABLE [dbo].[historial_estado_evidencia] WITH CHECK ADD CONSTRAINT [fk_hist_estado_evid_registro]
        FOREIGN KEY([id_registro]) REFERENCES [dbo].[registro_evidencia] ([id_registro]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_hist_estado_evid_estado_anterior')
    ALTER TABLE [dbo].[historial_estado_evidencia] WITH CHECK ADD CONSTRAINT [fk_hist_estado_evid_estado_anterior]
        FOREIGN KEY([id_estado_anterior]) REFERENCES [dbo].[estado_evidencia] ([id_estado_evidencia]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_hist_estado_evid_estado_nuevo')
    ALTER TABLE [dbo].[historial_estado_evidencia] WITH CHECK ADD CONSTRAINT [fk_hist_estado_evid_estado_nuevo]
        FOREIGN KEY([id_estado_nuevo]) REFERENCES [dbo].[estado_evidencia] ([id_estado_evidencia]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_hist_estado_evid_usuario')
    ALTER TABLE [dbo].[historial_estado_evidencia] WITH CHECK ADD CONSTRAINT [fk_hist_estado_evid_usuario]
        FOREIGN KEY([id_usuario]) REFERENCES [dbo].[usuario] ([id_user]);
GO

/* ---------- Institutional hierarchy ---------- */
IF OBJECT_ID(N'[dbo].[area_institucional]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[area_institucional](
        [id_area] [int] IDENTITY(1,1) NOT NULL,
        [codigo_area] [varchar](20) NOT NULL,
        [nombre_area] [varchar](150) NOT NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_area_institucional_activo] DEFAULT ((1)),
        CONSTRAINT [pk_area_institucional] PRIMARY KEY CLUSTERED ([id_area] ASC),
        CONSTRAINT [uq_area_institucional_codigo] UNIQUE NONCLUSTERED ([codigo_area] ASC)
    );
END
GO

IF OBJECT_ID(N'[dbo].[cargo_area]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[cargo_area](
        [id_cargo] [int] IDENTITY(1,1) NOT NULL,
        [id_area] [int] NOT NULL,
        [codigo_cargo] [varchar](30) NOT NULL,
        [nombre_cargo] [varchar](150) NOT NULL,
        [nivel_jerarquico] [int] NOT NULL,
        [aprueba_interno] [bit] NOT NULL CONSTRAINT [df_cargo_area_aprueba] DEFAULT ((0)),
        [activo] [bit] NOT NULL CONSTRAINT [df_cargo_area_activo] DEFAULT ((1)),
        CONSTRAINT [pk_cargo_area] PRIMARY KEY CLUSTERED ([id_cargo] ASC),
        CONSTRAINT [uq_cargo_area] UNIQUE NONCLUSTERED ([id_area], [codigo_cargo]),
        CONSTRAINT [ck_cargo_area_nivel] CHECK ([nivel_jerarquico] > 0)
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_cargo_area_area')
    ALTER TABLE [dbo].[cargo_area] WITH CHECK ADD CONSTRAINT [fk_cargo_area_area]
        FOREIGN KEY([id_area]) REFERENCES [dbo].[area_institucional] ([id_area]);
GO

IF OBJECT_ID(N'[dbo].[usuario_area_cargo]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[usuario_area_cargo](
        [id_usuario_area_cargo] [int] IDENTITY(1,1) NOT NULL,
        [id_user] [int] NOT NULL,
        [id_area] [int] NOT NULL,
        [id_cargo] [int] NOT NULL,
        [fecha_asignacion] [datetime2](0) NOT NULL CONSTRAINT [df_usuario_area_cargo_fecha] DEFAULT (sysutcdatetime()),
        [activo] [bit] NOT NULL CONSTRAINT [df_usuario_area_cargo_activo] DEFAULT ((1)),
        CONSTRAINT [pk_usuario_area_cargo] PRIMARY KEY CLUSTERED ([id_usuario_area_cargo] ASC),
        CONSTRAINT [uq_usuario_area_cargo] UNIQUE NONCLUSTERED ([id_user], [id_area], [id_cargo], [activo])
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_usuario_area_cargo_usuario')
    ALTER TABLE [dbo].[usuario_area_cargo] WITH CHECK ADD CONSTRAINT [fk_usuario_area_cargo_usuario]
        FOREIGN KEY([id_user]) REFERENCES [dbo].[usuario] ([id_user]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_usuario_area_cargo_area')
    ALTER TABLE [dbo].[usuario_area_cargo] WITH CHECK ADD CONSTRAINT [fk_usuario_area_cargo_area]
        FOREIGN KEY([id_area]) REFERENCES [dbo].[area_institucional] ([id_area]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_usuario_area_cargo_cargo')
    ALTER TABLE [dbo].[usuario_area_cargo] WITH CHECK ADD CONSTRAINT [fk_usuario_area_cargo_cargo]
        FOREIGN KEY([id_cargo]) REFERENCES [dbo].[cargo_area] ([id_cargo]);
GO

IF OBJECT_ID(N'[dbo].[usuario_supervisor]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[usuario_supervisor](
        [id_usuario_supervisor] [int] IDENTITY(1,1) NOT NULL,
        [id_user] [int] NOT NULL,
        [id_supervisor] [int] NOT NULL,
        [fecha_asignacion] [datetime2](0) NOT NULL CONSTRAINT [df_usuario_supervisor_fecha] DEFAULT (sysutcdatetime()),
        [activo] [bit] NOT NULL CONSTRAINT [df_usuario_supervisor_activo] DEFAULT ((1)),
        CONSTRAINT [pk_usuario_supervisor] PRIMARY KEY CLUSTERED ([id_usuario_supervisor] ASC),
        CONSTRAINT [uq_usuario_supervisor] UNIQUE NONCLUSTERED ([id_user], [id_supervisor], [activo]),
        CONSTRAINT [ck_usuario_supervisor_distinto] CHECK ([id_user] <> [id_supervisor])
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_usuario_supervisor_usuario')
    ALTER TABLE [dbo].[usuario_supervisor] WITH CHECK ADD CONSTRAINT [fk_usuario_supervisor_usuario]
        FOREIGN KEY([id_user]) REFERENCES [dbo].[usuario] ([id_user]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_usuario_supervisor_supervisor')
    ALTER TABLE [dbo].[usuario_supervisor] WITH CHECK ADD CONSTRAINT [fk_usuario_supervisor_supervisor]
        FOREIGN KEY([id_supervisor]) REFERENCES [dbo].[usuario] ([id_user]);
GO

/* ---------- CACES support tables ---------- */
IF OBJECT_ID(N'[dbo].[categoria_valoracion_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[categoria_valoracion_caces](
        [id_categoria] [int] IDENTITY(1,1) NOT NULL,
        [codigo] [varchar](40) NOT NULL,
        [nombre] [varchar](120) NOT NULL,
        [utilidad] [decimal](5,2) NOT NULL,
        [descripcion] [varchar](500) NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_categoria_caces_activo] DEFAULT ((1)),
        CONSTRAINT [pk_categoria_valoracion_caces] PRIMARY KEY CLUSTERED ([id_categoria] ASC),
        CONSTRAINT [uq_categoria_valoracion_caces_codigo] UNIQUE NONCLUSTERED ([codigo] ASC)
    );
END
GO

IF OBJECT_ID(N'[dbo].[escenario_ponderacion_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[escenario_ponderacion_caces](
        [codigo_escenario] [varchar](1) NOT NULL,
        [nombre] [varchar](120) NOT NULL,
        [descripcion] [varchar](500) NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_escenario_caces_activo] DEFAULT ((1)),
        CONSTRAINT [pk_escenario_ponderacion_caces] PRIMARY KEY CLUSTERED ([codigo_escenario] ASC)
    );
END
GO

IF OBJECT_ID(N'[dbo].[modelo_indicador_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[modelo_indicador_caces](
        [id_modelo_indicador] [int] IDENTITY(1,1) NOT NULL,
        [numero_modelo] [int] NOT NULL,
        [codigo_modelo] [varchar](20) NOT NULL,
        [criterio] [varchar](120) NOT NULL,
        [subcriterio] [varchar](180) NULL,
        [nombre_indicador] [varchar](250) NOT NULL,
        [tipo_evaluacion] [varchar](20) NOT NULL,
        [ponderacion_a] [decimal](10,4) NOT NULL,
        [ponderacion_b] [decimal](10,4) NULL,
        [ponderacion_c] [decimal](10,4) NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_modelo_indicador_caces_activo] DEFAULT ((1)),
        CONSTRAINT [pk_modelo_indicador_caces] PRIMARY KEY CLUSTERED ([id_modelo_indicador] ASC),
        CONSTRAINT [uq_modelo_indicador_caces_numero] UNIQUE NONCLUSTERED ([numero_modelo] ASC),
        CONSTRAINT [uq_modelo_indicador_caces_codigo] UNIQUE NONCLUSTERED ([codigo_modelo] ASC),
        CONSTRAINT [ck_modelo_indicador_caces_tipo] CHECK ([tipo_evaluacion] IN ('CUALITATIVO', 'CUANTITATIVO'))
    );
END
GO

IF OBJECT_ID(N'[dbo].[indicador_caces_mapeo]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[indicador_caces_mapeo](
        [id_mapeo] [int] IDENTITY(1,1) NOT NULL,
        [id_indicador] [int] NOT NULL,
        [numero_modelo] [int] NOT NULL,
        [fecha_mapeo] [datetime2](0) NULL CONSTRAINT [df_indicador_caces_mapeo_fecha] DEFAULT (sysutcdatetime()),
        [observacion] [varchar](500) NULL,
        CONSTRAINT [pk_indicador_caces_mapeo] PRIMARY KEY CLUSTERED ([id_mapeo] ASC),
        CONSTRAINT [uq_indicador_caces_mapeo_indicador] UNIQUE NONCLUSTERED ([id_indicador] ASC),
        CONSTRAINT [uq_indicador_caces_mapeo_modelo] UNIQUE NONCLUSTERED ([numero_modelo] ASC)
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_indicador_caces_mapeo_indicador')
    ALTER TABLE [dbo].[indicador_caces_mapeo] WITH CHECK ADD CONSTRAINT [fk_indicador_caces_mapeo_indicador]
        FOREIGN KEY([id_indicador]) REFERENCES [dbo].[indicador] ([id_indicador]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_indicador_caces_mapeo_modelo')
    ALTER TABLE [dbo].[indicador_caces_mapeo] WITH CHECK ADD CONSTRAINT [fk_indicador_caces_mapeo_modelo]
        FOREIGN KEY([numero_modelo]) REFERENCES [dbo].[modelo_indicador_caces] ([numero_modelo]);
GO

IF OBJECT_ID(N'[dbo].[ciclo_configuracion_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[ciclo_configuracion_caces](
        [id_ciclo] [int] NOT NULL,
        [codigo_escenario] [varchar](1) NOT NULL,
        [observacion] [varchar](500) NULL,
        [fecha_configuracion] [datetime2](0) NULL CONSTRAINT [df_ciclo_config_caces_fecha] DEFAULT (sysutcdatetime()),
        CONSTRAINT [pk_ciclo_configuracion_caces] PRIMARY KEY CLUSTERED ([id_ciclo] ASC)
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_ciclo_config_caces_ciclo')
    ALTER TABLE [dbo].[ciclo_configuracion_caces] WITH CHECK ADD CONSTRAINT [fk_ciclo_config_caces_ciclo]
        FOREIGN KEY([id_ciclo]) REFERENCES [dbo].[ciclo_evaluacion] ([id_ciclo]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_ciclo_config_caces_escenario')
    ALTER TABLE [dbo].[ciclo_configuracion_caces] WITH CHECK ADD CONSTRAINT [fk_ciclo_config_caces_escenario]
        FOREIGN KEY([codigo_escenario]) REFERENCES [dbo].[escenario_ponderacion_caces] ([codigo_escenario]);
GO

IF OBJECT_ID(N'[dbo].[indicador_formula_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[indicador_formula_caces](
        [id_formula] [int] IDENTITY(1,1) NOT NULL,
        [numero_modelo] [int] NOT NULL,
        [codigo_formula] [varchar](50) NOT NULL,
        [nombre_formula] [varchar](250) NOT NULL,
        [expresion_formula] [varchar](1000) NOT NULL,
        [estandar] [decimal](18,4) NOT NULL,
        [sentido_calculo] [varchar](20) NOT NULL,
        [activo] [bit] NOT NULL CONSTRAINT [df_formula_caces_activo] DEFAULT ((1)),
        CONSTRAINT [pk_indicador_formula_caces] PRIMARY KEY CLUSTERED ([id_formula] ASC),
        CONSTRAINT [uq_indicador_formula_caces_modelo] UNIQUE NONCLUSTERED ([numero_modelo] ASC),
        CONSTRAINT [uq_indicador_formula_caces_codigo] UNIQUE NONCLUSTERED ([codigo_formula] ASC),
        CONSTRAINT [ck_formula_caces_sentido] CHECK ([sentido_calculo] IN ('MAYOR_IGUAL', 'MENOR_IGUAL'))
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_formula_caces_modelo')
    ALTER TABLE [dbo].[indicador_formula_caces] WITH CHECK ADD CONSTRAINT [fk_formula_caces_modelo]
        FOREIGN KEY([numero_modelo]) REFERENCES [dbo].[modelo_indicador_caces] ([numero_modelo]);
GO

IF OBJECT_ID(N'[dbo].[indicador_formula_variable_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[indicador_formula_variable_caces](
        [id_formula_variable] [int] IDENTITY(1,1) NOT NULL,
        [codigo_formula] [varchar](50) NOT NULL,
        [codigo_variable] [varchar](50) NOT NULL,
        [nombre_variable] [varchar](250) NOT NULL,
        [descripcion] [varchar](1000) NULL,
        [obligatorio] [bit] NOT NULL CONSTRAINT [df_formula_variable_caces_obligatorio] DEFAULT ((1)),
        CONSTRAINT [pk_indicador_formula_variable_caces] PRIMARY KEY CLUSTERED ([id_formula_variable] ASC),
        CONSTRAINT [uq_indicador_formula_variable_caces] UNIQUE NONCLUSTERED ([codigo_formula], [codigo_variable])
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_formula_variable_caces_formula')
    ALTER TABLE [dbo].[indicador_formula_variable_caces] WITH CHECK ADD CONSTRAINT [fk_formula_variable_caces_formula]
        FOREIGN KEY([codigo_formula]) REFERENCES [dbo].[indicador_formula_caces] ([codigo_formula]);
GO

IF OBJECT_ID(N'[dbo].[evaluacion_variable_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[evaluacion_variable_caces](
        [id_variable_evaluacion] [int] IDENTITY(1,1) NOT NULL,
        [id_ciclo] [int] NOT NULL,
        [id_indicador] [int] NOT NULL,
        [codigo_variable] [varchar](50) NOT NULL,
        [nombre_variable] [varchar](250) NOT NULL,
        [valor_variable] [decimal](18,4) NOT NULL,
        [observacion] [varchar](500) NULL,
        [registrado_por] [int] NULL,
        [fecha_registro] [datetime2](0) NULL CONSTRAINT [df_eval_variable_caces_fecha] DEFAULT (sysutcdatetime()),
        CONSTRAINT [pk_evaluacion_variable_caces] PRIMARY KEY CLUSTERED ([id_variable_evaluacion] ASC),
        CONSTRAINT [uq_evaluacion_variable_caces] UNIQUE NONCLUSTERED ([id_ciclo], [id_indicador], [codigo_variable])
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_variable_caces_ciclo')
    ALTER TABLE [dbo].[evaluacion_variable_caces] WITH CHECK ADD CONSTRAINT [fk_eval_variable_caces_ciclo]
        FOREIGN KEY([id_ciclo]) REFERENCES [dbo].[ciclo_evaluacion] ([id_ciclo]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_variable_caces_indicador')
    ALTER TABLE [dbo].[evaluacion_variable_caces] WITH CHECK ADD CONSTRAINT [fk_eval_variable_caces_indicador]
        FOREIGN KEY([id_indicador]) REFERENCES [dbo].[indicador] ([id_indicador]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_variable_caces_usuario')
    ALTER TABLE [dbo].[evaluacion_variable_caces] WITH CHECK ADD CONSTRAINT [fk_eval_variable_caces_usuario]
        FOREIGN KEY([registrado_por]) REFERENCES [dbo].[usuario] ([id_user]);
GO

IF OBJECT_ID(N'[dbo].[evaluacion_indicador_caces]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[evaluacion_indicador_caces](
        [id_evaluacion_indicador] [int] IDENTITY(1,1) NOT NULL,
        [id_ciclo] [int] NOT NULL,
        [id_indicador] [int] NOT NULL,
        [numero_modelo] [int] NULL,
        [tipo_evaluacion] [varchar](20) NOT NULL,
        [id_categoria] [int] NULL,
        [codigo_formula] [varchar](50) NULL,
        [valor_calculado] [decimal](18,4) NULL,
        [estandar] [decimal](18,4) NULL,
        [sentido_calculo] [varchar](20) NULL,
        [utilidad] [decimal](10,4) NOT NULL,
        [ponderacion] [decimal](10,4) NOT NULL,
        [aporte] [decimal](12,6) NOT NULL,
        [observacion] [varchar](1000) NULL,
        [calculado_por] [int] NULL,
        [fecha_calculo] [datetime2](0) NULL CONSTRAINT [df_eval_indicador_caces_fecha] DEFAULT (sysutcdatetime()),
        CONSTRAINT [pk_evaluacion_indicador_caces] PRIMARY KEY CLUSTERED ([id_evaluacion_indicador] ASC),
        CONSTRAINT [uq_evaluacion_indicador_caces] UNIQUE NONCLUSTERED ([id_ciclo], [id_indicador]),
        CONSTRAINT [ck_eval_indicador_caces_tipo] CHECK ([tipo_evaluacion] IN ('CUALITATIVO', 'CUANTITATIVO'))
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_indicador_caces_ciclo')
    ALTER TABLE [dbo].[evaluacion_indicador_caces] WITH CHECK ADD CONSTRAINT [fk_eval_indicador_caces_ciclo]
        FOREIGN KEY([id_ciclo]) REFERENCES [dbo].[ciclo_evaluacion] ([id_ciclo]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_indicador_caces_indicador')
    ALTER TABLE [dbo].[evaluacion_indicador_caces] WITH CHECK ADD CONSTRAINT [fk_eval_indicador_caces_indicador]
        FOREIGN KEY([id_indicador]) REFERENCES [dbo].[indicador] ([id_indicador]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_indicador_caces_categoria')
    ALTER TABLE [dbo].[evaluacion_indicador_caces] WITH CHECK ADD CONSTRAINT [fk_eval_indicador_caces_categoria]
        FOREIGN KEY([id_categoria]) REFERENCES [dbo].[categoria_valoracion_caces] ([id_categoria]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_eval_indicador_caces_usuario')
    ALTER TABLE [dbo].[evaluacion_indicador_caces] WITH CHECK ADD CONSTRAINT [fk_eval_indicador_caces_usuario]
        FOREIGN KEY([calculado_por]) REFERENCES [dbo].[usuario] ([id_user]);
GO

/* ---------- Bridge synchronization and reporting views ---------- */
IF OBJECT_ID(N'[dbo].[indicador_elemento_fundamental]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[indicador_elemento_fundamental](
        [id_indicador] [int] NOT NULL,
        [id_elemento_fundamental] [int] NOT NULL,
        CONSTRAINT [pk_indicador_elemento_fundamental]
            PRIMARY KEY CLUSTERED ([id_indicador] ASC, [id_elemento_fundamental] ASC)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_ief_indicador')
    ALTER TABLE [dbo].[indicador_elemento_fundamental] WITH CHECK ADD CONSTRAINT [fk_ief_indicador]
        FOREIGN KEY([id_indicador]) REFERENCES [dbo].[indicador] ([id_indicador]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'fk_ief_elemento')
    ALTER TABLE [dbo].[indicador_elemento_fundamental] WITH CHECK ADD CONSTRAINT [fk_ief_elemento]
        FOREIGN KEY([id_elemento_fundamental]) REFERENCES [dbo].[elemento_fundamental] ([id_elemento_fundamental]);
GO

INSERT INTO [dbo].[indicador_elemento_fundamental] ([id_indicador], [id_elemento_fundamental])
SELECT ef.[id_indicador], ef.[id_elemento_fundamental]
FROM [dbo].[elemento_fundamental] ef
WHERE NOT EXISTS (
    SELECT 1
    FROM [dbo].[indicador_elemento_fundamental] ief
    WHERE ief.[id_indicador] = ef.[id_indicador]
      AND ief.[id_elemento_fundamental] = ef.[id_elemento_fundamental]
);
GO

CREATE OR ALTER TRIGGER [dbo].[trg_elemento_fundamental_sync_ief]
ON [dbo].[elemento_fundamental]
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    DELETE ief
    FROM [dbo].[indicador_elemento_fundamental] ief
    JOIN inserted i
        ON i.[id_elemento_fundamental] = ief.[id_elemento_fundamental]
    WHERE ief.[id_indicador] <> i.[id_indicador];

    INSERT INTO [dbo].[indicador_elemento_fundamental] ([id_indicador], [id_elemento_fundamental])
    SELECT i.[id_indicador], i.[id_elemento_fundamental]
    FROM inserted i
    WHERE NOT EXISTS (
        SELECT 1
        FROM [dbo].[indicador_elemento_fundamental] ief
        WHERE ief.[id_indicador] = i.[id_indicador]
          AND ief.[id_elemento_fundamental] = i.[id_elemento_fundamental]
    );
END
GO

CREATE OR ALTER TRIGGER [dbo].[trg_registro_evidencia_historial_estado]
ON [dbo].[registro_evidencia]
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [dbo].[historial_estado_evidencia] (
        [id_registro],
        [id_estado_anterior],
        [id_estado_nuevo],
        [id_usuario],
        [tipo_evento],
        [fecha_evento],
        [comentario]
    )
    SELECT
        i.[id_registro],
        d.[id_estado_evidencia],
        i.[id_estado_evidencia],
        COALESCE(i.[enviado_revision_por], i.[registrado_por]),
        CASE
            WHEN d.[id_registro] IS NULL THEN 'CREACION'
            WHEN ISNULL(d.[id_estado_evidencia], -1) <> ISNULL(i.[id_estado_evidencia], -1) THEN 'CAMBIO_ESTADO'
            WHEN d.[fecha_envio_revision] IS NULL AND i.[fecha_envio_revision] IS NOT NULL THEN 'ENVIO_REVISION'
            ELSE 'ACTUALIZACION'
        END,
        sysutcdatetime(),
        i.[comentario]
    FROM inserted i
    LEFT JOIN deleted d
        ON d.[id_registro] = i.[id_registro]
    WHERE d.[id_registro] IS NULL
       OR ISNULL(d.[id_estado_evidencia], -1) <> ISNULL(i.[id_estado_evidencia], -1)
       OR (d.[fecha_envio_revision] IS NULL AND i.[fecha_envio_revision] IS NOT NULL);
END
GO

CREATE OR ALTER VIEW [dbo].[vw_matriz_acreditacion]
AS
WITH indicador_elementos AS (
    SELECT [id_indicador], [id_elemento_fundamental]
    FROM [dbo].[indicador_elemento_fundamental]
    UNION
    SELECT [id_indicador], [id_elemento_fundamental]
    FROM [dbo].[elemento_fundamental]
)
SELECT
    c.[id_criterio],
    c.[codigo_criterio],
    c.[nombre_criterio],
    sc.[id_subcriterio],
    sc.[codigo_subcriterio],
    sc.[nombre_subcriterio],
    i.[id_indicador],
    i.[codigo_indicador],
    i.[nombre_indicador],
    ef.[id_elemento_fundamental],
    ef.[codigo_elemento],
    ef.[nombre_elemento]
FROM [dbo].[criterio] c
JOIN [dbo].[subcriterio] sc
    ON sc.[id_criterio] = c.[id_criterio]
JOIN [dbo].[indicador] i
    ON i.[id_subcriterio] = sc.[id_subcriterio]
LEFT JOIN indicador_elementos ief
    ON ief.[id_indicador] = i.[id_indicador]
LEFT JOIN [dbo].[elemento_fundamental] ef
    ON ef.[id_elemento_fundamental] = ief.[id_elemento_fundamental];
GO

CREATE OR ALTER VIEW [dbo].[vw_estado_evidencias_ciclo]
AS
SELECT
    ce.[id_ciclo],
    ce.[nombre] AS [ciclo],
    i.[id_indicador],
    i.[codigo_indicador],
    i.[nombre_indicador],
    ef.[id_elemento_fundamental],
    ef.[codigo_elemento],
    ef.[nombre_elemento],
    ee.[descripcion] AS [estado_evidencia],
    COUNT(*) AS [total]
FROM [dbo].[registro_evidencia] re
JOIN [dbo].[ciclo_evaluacion] ce
    ON ce.[id_ciclo] = re.[id_ciclo]
JOIN [dbo].[indicador] i
    ON i.[id_indicador] = re.[id_indicador]
JOIN [dbo].[elemento_fundamental] ef
    ON ef.[id_elemento_fundamental] = re.[id_elemento_fundamental]
JOIN [dbo].[estado_evidencia] ee
    ON ee.[id_estado_evidencia] = re.[id_estado_evidencia]
GROUP BY
    ce.[id_ciclo],
    ce.[nombre],
    i.[id_indicador],
    i.[codigo_indicador],
    i.[nombre_indicador],
    ef.[id_elemento_fundamental],
    ef.[codigo_elemento],
    ef.[nombre_elemento],
    ee.[descripcion];
GO

/* ---------- Minimum operational catalogs ---------- */
IF NOT EXISTS (SELECT 1 FROM [dbo].[tipo_identificacion] WHERE UPPER([descripcion]) = 'CEDULA')
    INSERT INTO [dbo].[tipo_identificacion] ([descripcion], [activo]) VALUES ('CEDULA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[tipo_identificacion] WHERE UPPER([descripcion]) = 'PASAPORTE')
    INSERT INTO [dbo].[tipo_identificacion] ([descripcion], [activo]) VALUES ('PASAPORTE', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[tipo_identificacion] WHERE UPPER([descripcion]) = 'RUC')
    INSERT INTO [dbo].[tipo_identificacion] ([descripcion], [activo]) VALUES ('RUC', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[tipo_indicador] WHERE UPPER([descripcion]) = 'CUALITATIVO')
    INSERT INTO [dbo].[tipo_indicador] ([descripcion], [activo]) VALUES ('CUALITATIVO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[tipo_indicador] WHERE UPPER([descripcion]) = 'CUANTITATIVO')
    INSERT INTO [dbo].[tipo_indicador] ([descripcion], [activo]) VALUES ('CUANTITATIVO', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_ciclo] WHERE UPPER([descripcion]) = 'BORRADOR')
    INSERT INTO [dbo].[estado_ciclo] ([descripcion], [activo]) VALUES ('BORRADOR', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_ciclo] WHERE UPPER([descripcion]) = 'APROBADO')
    INSERT INTO [dbo].[estado_ciclo] ([descripcion], [activo]) VALUES ('APROBADO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_ciclo] WHERE UPPER([descripcion]) = 'ACTIVO')
    INSERT INTO [dbo].[estado_ciclo] ([descripcion], [activo]) VALUES ('ACTIVO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_ciclo] WHERE UPPER([descripcion]) = 'EN_FINALIZACION')
    INSERT INTO [dbo].[estado_ciclo] ([descripcion], [activo]) VALUES ('EN_FINALIZACION', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_ciclo] WHERE UPPER([descripcion]) = 'CERRADO')
    INSERT INTO [dbo].[estado_ciclo] ([descripcion], [activo]) VALUES ('CERRADO', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'CARGADA')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('CARGADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'ENVIADA_EVALUADOR')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('ENVIADA_EVALUADOR', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'EN_REVISION_EVALUADOR')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('EN_REVISION_EVALUADOR', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'APROBADA')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('APROBADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'OBSERVADA')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('OBSERVADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evidencia] WHERE UPPER([descripcion]) = 'RECHAZADA')
    INSERT INTO [dbo].[estado_evidencia] ([descripcion], [activo]) VALUES ('RECHAZADA', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evaluacion] WHERE UPPER([descripcion]) = 'EN_ANALISIS')
    INSERT INTO [dbo].[estado_evaluacion] ([descripcion], [activo]) VALUES ('EN_ANALISIS', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evaluacion] WHERE UPPER([descripcion]) = 'APROBADA')
    INSERT INTO [dbo].[estado_evaluacion] ([descripcion], [activo]) VALUES ('APROBADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evaluacion] WHERE UPPER([descripcion]) = 'OBSERVADA')
    INSERT INTO [dbo].[estado_evaluacion] ([descripcion], [activo]) VALUES ('OBSERVADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_evaluacion] WHERE UPPER([descripcion]) = 'RECHAZADA')
    INSERT INTO [dbo].[estado_evaluacion] ([descripcion], [activo]) VALUES ('RECHAZADA', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'PENDIENTE')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('PENDIENTE', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'EN_PROGRESO')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('EN_PROGRESO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'CARGADA')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('CARGADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'ENVIADA_REVISION')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('ENVIADA_REVISION', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'OBSERVADA')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('OBSERVADA', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_tarea_evidencia] WHERE UPPER([descripcion]) = 'CERRADA')
    INSERT INTO [dbo].[estado_tarea_evidencia] ([descripcion], [activo]) VALUES ('CERRADA', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_informe] WHERE UPPER([descripcion]) = 'BORRADOR')
    INSERT INTO [dbo].[estado_informe] ([descripcion], [activo]) VALUES ('BORRADOR', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_informe] WHERE UPPER([descripcion]) = 'GENERADO')
    INSERT INTO [dbo].[estado_informe] ([descripcion], [activo]) VALUES ('GENERADO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_informe] WHERE UPPER([descripcion]) = 'APROBADO')
    INSERT INTO [dbo].[estado_informe] ([descripcion], [activo]) VALUES ('APROBADO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_informe] WHERE UPPER([descripcion]) = 'OBSERVADO')
    INSERT INTO [dbo].[estado_informe] ([descripcion], [activo]) VALUES ('OBSERVADO', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_plan_mejora] WHERE UPPER([descripcion]) = 'ABIERTO')
    INSERT INTO [dbo].[estado_plan_mejora] ([descripcion], [activo]) VALUES ('ABIERTO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_plan_mejora] WHERE UPPER([descripcion]) = 'EN_PROGRESO')
    INSERT INTO [dbo].[estado_plan_mejora] ([descripcion], [activo]) VALUES ('EN_PROGRESO', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[estado_plan_mejora] WHERE UPPER([descripcion]) = 'CERRADO')
    INSERT INTO [dbo].[estado_plan_mejora] ([descripcion], [activo]) VALUES ('CERRADO', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_documento] WHERE [codigo] = 'PUBLICO')
    INSERT INTO [dbo].[clasificacion_documento] ([codigo], [nombre], [nivel_confidencialidad], [requiere_cifrado], [activo])
    VALUES ('PUBLICO', 'Publico', 'PUBLICO', 0, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_documento] WHERE [codigo] = 'INTERNO')
    INSERT INTO [dbo].[clasificacion_documento] ([codigo], [nombre], [nivel_confidencialidad], [requiere_cifrado], [activo])
    VALUES ('INTERNO', 'Interno', 'INTERNO', 0, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_documento] WHERE [codigo] = 'CONFIDENCIAL')
    INSERT INTO [dbo].[clasificacion_documento] ([codigo], [nombre], [nivel_confidencialidad], [requiere_cifrado], [activo])
    VALUES ('CONFIDENCIAL', 'Confidencial', 'CONFIDENCIAL', 1, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_documento] WHERE [codigo] = 'RESTRINGIDO')
    INSERT INTO [dbo].[clasificacion_documento] ([codigo], [nombre], [nivel_confidencialidad], [requiere_cifrado], [activo])
    VALUES ('RESTRINGIDO', 'Restringido', 'RESTRINGIDO', 1, 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_elemento_fundamental] WHERE [codigo] = 'ESENCIAL')
    INSERT INTO [dbo].[clasificacion_elemento_fundamental] ([codigo], [nombre], [activo])
    VALUES ('ESENCIAL', 'Esencial', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[clasificacion_elemento_fundamental] WHERE [codigo] = 'COMPLEMENTARIO')
    INSERT INTO [dbo].[clasificacion_elemento_fundamental] ([codigo], [nombre], [activo])
    VALUES ('COMPLEMENTARIO', 'Complementario', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[rol] WHERE UPPER([nombre_rol]) = 'ADMINISTRADOR')
    INSERT INTO [dbo].[rol] ([nombre_rol], [descripcion], [acceso_global], [activo]) VALUES ('ADMINISTRADOR', 'Acceso total al sistema', 1, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[rol] WHERE UPPER([nombre_rol]) = 'CALIDAD ACADEMICA')
    INSERT INTO [dbo].[rol] ([nombre_rol], [descripcion], [acceso_global], [activo]) VALUES ('CALIDAD ACADEMICA', 'Gestion de acreditacion y calidad', 0, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[rol] WHERE UPPER([nombre_rol]) = 'RECTOR')
    INSERT INTO [dbo].[rol] ([nombre_rol], [descripcion], [acceso_global], [activo]) VALUES ('RECTOR', 'Aprobacion institucional', 0, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[rol] WHERE UPPER([nombre_rol]) = 'EVALUADOR')
    INSERT INTO [dbo].[rol] ([nombre_rol], [descripcion], [acceso_global], [activo]) VALUES ('EVALUADOR', 'Revision de evidencias', 0, 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[rol] WHERE UPPER([nombre_rol]) = 'CONSULTA')
    INSERT INTO [dbo].[rol] ([nombre_rol], [descripcion], [acceso_global], [activo]) VALUES ('CONSULTA', 'Acceso de solo lectura', 0, 1);
GO

DECLARE @permisos TABLE ([codigo] varchar(100), [descripcion] varchar(250), [modulo] varchar(100));
INSERT INTO @permisos ([codigo], [descripcion], [modulo])
VALUES
('usuarios.ver', 'Ver usuarios', 'usuarios'),
('usuarios.crear', 'Crear usuarios', 'usuarios'),
('usuarios.editar', 'Editar usuarios', 'usuarios'),
('roles.gestionar', 'Gestionar roles y permisos', 'permisos'),
('acreditacion.gestionar', 'Gestionar modelo de acreditacion', 'acreditacion'),
('acreditacion.ver', 'Ver modelo de acreditacion', 'acreditacion'),
('evidencias.registrar', 'Registrar evidencias', 'evidencias'),
('documentos.ver', 'Ver documentos', 'documentos'),
('evaluacion.revisar', 'Revisar evidencias', 'evaluacion'),
('informes.generar', 'Generar informes', 'informes'),
('informes.aprobar', 'Aprobar informes', 'informes'),
('mejora.gestionar', 'Gestionar planes de mejora', 'mejora'),
('consulta.ver', 'Consulta de solo lectura', 'consulta');

INSERT INTO [dbo].[permiso] ([codigo_permiso], [descripcion], [modulo], [activo])
SELECT p.[codigo], p.[descripcion], p.[modulo], 1
FROM @permisos p
WHERE NOT EXISTS (
    SELECT 1 FROM [dbo].[permiso] x WHERE x.[codigo_permiso] = p.[codigo]
);

INSERT INTO [dbo].[rol_permiso] ([id_rol], [id_permiso])
SELECT r.[id_rol], p.[id_permiso]
FROM [dbo].[rol] r
CROSS JOIN [dbo].[permiso] p
WHERE UPPER(r.[nombre_rol]) = 'ADMINISTRADOR'
  AND NOT EXISTS (
      SELECT 1
      FROM [dbo].[rol_permiso] rp
      WHERE rp.[id_rol] = r.[id_rol]
        AND rp.[id_permiso] = p.[id_permiso]
  );
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[categoria_valoracion_caces] WHERE [codigo] = 'SATISFACTORIO')
    INSERT INTO [dbo].[categoria_valoracion_caces] ([codigo], [nombre], [utilidad], [descripcion], [activo])
    VALUES ('SATISFACTORIO', 'Satisfactorio', 1.00, 'Cumplimiento pleno del criterio cualitativo.', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[categoria_valoracion_caces] WHERE [codigo] = 'CUASI_SATISFACTORIO')
    INSERT INTO [dbo].[categoria_valoracion_caces] ([codigo], [nombre], [utilidad], [descripcion], [activo])
    VALUES ('CUASI_SATISFACTORIO', 'Cuasi satisfactorio', 0.70, 'Cumplimiento mayoritario con aspectos por fortalecer.', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[categoria_valoracion_caces] WHERE [codigo] = 'POCO_SATISFACTORIO')
    INSERT INTO [dbo].[categoria_valoracion_caces] ([codigo], [nombre], [utilidad], [descripcion], [activo])
    VALUES ('POCO_SATISFACTORIO', 'Poco satisfactorio', 0.35, 'Cumplimiento parcial con brechas relevantes.', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[categoria_valoracion_caces] WHERE [codigo] = 'DEFICIENTE')
    INSERT INTO [dbo].[categoria_valoracion_caces] ([codigo], [nombre], [utilidad], [descripcion], [activo])
    VALUES ('DEFICIENTE', 'Deficiente', 0.00, 'No cumple el criterio cualitativo.', 1);
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[escenario_ponderacion_caces] WHERE [codigo_escenario] = 'A')
    INSERT INTO [dbo].[escenario_ponderacion_caces] ([codigo_escenario], [nombre], [descripcion], [activo])
    VALUES ('A', 'Escenario A', 'Ponderacion principal CACES.', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[escenario_ponderacion_caces] WHERE [codigo_escenario] = 'B')
    INSERT INTO [dbo].[escenario_ponderacion_caces] ([codigo_escenario], [nombre], [descripcion], [activo])
    VALUES ('B', 'Escenario B', 'Ponderacion alternativa CACES.', 1);
IF NOT EXISTS (SELECT 1 FROM [dbo].[escenario_ponderacion_caces] WHERE [codigo_escenario] = 'C')
    INSERT INTO [dbo].[escenario_ponderacion_caces] ([codigo_escenario], [nombre], [descripcion], [activo])
    VALUES ('C', 'Escenario C', 'Ponderacion alternativa CACES.', 1);
GO
