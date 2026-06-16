USE [$(DBName)]
GO

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
