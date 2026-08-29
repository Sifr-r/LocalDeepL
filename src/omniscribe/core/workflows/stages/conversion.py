from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from omniscribe.core.pdf import PDFHandler
from omniscribe.core.workflows.base import ProgressCallback, notify
from omniscribe.core.workflows.utils import parse_page_range

if TYPE_CHECKING:
    from omniscribe.core.imaging.page_preprocess import (
        PagePreprocessingOptions,
        PagePreprocessor,
    )


class HybridConverter:
    """Handles PDF rendering and page preprocessing for the hybrid workflow."""

    def __init__(
        self,
        pdf_handler: PDFHandler,
        page_preprocessor: PagePreprocessor | None = None,
    ) -> None:
        self.pdf_handler = pdf_handler
        self.page_preprocessor = page_preprocessor

    async def convert_pages(
        self,
        *,
        input_path: str,
        dpi: int,
        max_image_dim: int,
        pages: str | None,
        preprocessing_options: PagePreprocessingOptions | None,
        progress: ProgressCallback | None,
        rasterize_batch_size: int = 8,
    ) -> tuple[dict[int, str], list[int], dict[int, dict[str, object]]]:
        """Render the input to per-page images and apply optional preprocessing.

        Rasterization streams through :meth:`PDFHandler.convert_batches` with a
        bounded batch size so peak memory is independent of total page count. Each
        batch's PIL.Image objects are released as soon as their base64 strings are
        merged into the returned ``images_dict``.
        """
        await notify(progress, "convert", 0, 1, "Converting PDF to images...")
        images_dict: dict[int, str] = await asyncio.to_thread(
            self.collect_batched_images,
            input_path,
            dpi,
            max_image_dim,
            pages,
            rasterize_batch_size,
        )
        page_nums = sorted(images_dict.keys())
        total_pages = len(page_nums)

        preprocessing_metadata: dict[int, dict[str, object]] = {}
        if (
            self.page_preprocessor is not None
            and preprocessing_options is not None
            and preprocessing_options.enabled
        ):
            await notify(
                progress, "convert", 0, 1, f"Preprocessing {len(page_nums)} pages..."
            )
            preprocessing_result = await asyncio.to_thread(
                self.page_preprocessor.preprocess,
                images_dict,
                preprocessing_options,
            )
            images_dict = preprocessing_result.images
            preprocessing_metadata = preprocessing_result.metadata
        await notify(progress, "convert", 1, 1, f"Converted {total_pages} pages.")

        return images_dict, page_nums, preprocessing_metadata

    convert = convert_pages

    def collect_batched_images(
        self,
        input_path: str,
        dpi: int,
        max_image_dim: int,
        pages: str | None,
        batch_size: int,
    ) -> dict[int, str]:
        """Drive bounded-memory batched rasterization and merge b64 strings."""
        images_dict: dict[int, str] = {}

        if isinstance(self.pdf_handler, PDFHandler):
            for batch in self.pdf_handler.convert_batches(
                input_path,
                batch_size=batch_size,
                dpi=dpi,
                pages=pages,
                max_image_dim=max_image_dim,
            ):
                for page_num, _img, b64_str in batch:
                    images_dict[page_num] = b64_str
                del batch
            return images_dict

        all_images = self.pdf_handler.convert_to_images(
            input_path, dpi=dpi, max_image_dim=max_image_dim
        )
        if pages:
            selected = set(parse_page_range(pages, len(all_images)))
            return {p: img for p, img in all_images.items() if p in selected}
        return all_images
