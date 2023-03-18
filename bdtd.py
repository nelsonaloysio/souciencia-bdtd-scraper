#!/usr/bin/env python3

import logging as log
import os
import warnings
from argparse import ArgumentParser
from functools import partial
from requests import request
from time import sleep
from sys import argv
from typing import Union
from urllib.parse import urlparse
from urllib3.exceptions import InsecureRequestWarning

import pandas as pd
from bs4 import BeautifulSoup as bs
from tqdm.contrib.concurrent import process_map

log.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=log.INFO)

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

URL = "https://bdtd.ibict.br/vufind"

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:95.0) Gecko/20100101 Firefox/95.0",
}

INTERVAL = 0.5
MAX_RETRIES = 3
MAX_WORKERS = 8
RETRY_INTERVAL = 5
TIMEOUT = 10

class BDTD():

    def __init__(self, url: str = URL):
        """ Initializes class. """
        self.url = url

    @staticmethod
    def __call__(
        url,
        headers: dict = HEADERS,
        interval: int = INTERVAL,
        max_retries: int = MAX_RETRIES,
        timeout: int = TIMEOUT,
        verify: bool = True,
        **kwargs
    ) -> list:
        """ Returns content from requested URL. """
        current_try = 0
        while current_try < (max_retries or MAX_RETRIES):
            try:
                r = request("GET", url, headers=headers, timeout=timeout, verify=verify, **kwargs)
            except:
                log.warn(f"Returned status code {r.status_code}: '{r.reason}' from {url}.")
                current_try += 1
                sleep(RETRY_INTERVAL)
            else:
                sleep(interval or INTERVAL)
                return r
        return None

    def search(
        self,
        search_term: str,
        endpoint: str = "Search/Results",
        interval: int = INTERVAL,
        max_pages: int = None,
        max_retries: int = MAX_RETRIES,
        max_workers: int = MAX_WORKERS,
        parsed: bool = True,
        timeout: int = TIMEOUT,
        type: str = "AllFields",
    ) -> list:
        max_pages = max_pages or self._get_max_search_pages(
            self.__call__(
                "%s/%s?%s&%s&%s" % (
                    self.url,
                    endpoint,
                    f"lookfor={search_term}",
                    f"type={type}",
                    f"page=1",
                )
            )
        )

        urls = list(
            "%s/%s?%s&%s&%s" % (
                self.url,
                endpoint,
                f"lookfor={search_term}",
                f"type={type}",
                f"page={page}",
            )
            for page in range(
                max_pages
                if
                    max_pages
                else
                    self._get_total_pages(search_term, type=type)
                )
        )

        responses = process_map(
            partial(self.__call__, interval=interval, max_retries=max_retries),
            urls,
            ascii=True,
            chunksize=1,
            desc="Requisitando dados de busca",
            max_workers=max_workers,
            total=len(urls),
        )

        if parsed:
            df = pd.concat(self._pd_search(r) for r in responses)
            df.index = [_.split("Record/", 1)[-1].split("/", 1)[0] for _ in df["URL"]]
            return df.sort_index()

        return responses

    def get_records(
        self,
        records: Union[list, pd.Series, pd.DataFrame],
        endpoint: str = "Record",
        interval: int = INTERVAL,
        max_retries: int = MAX_RETRIES,
        max_workers: int = MAX_WORKERS,
        parsed: bool = True,
    ) -> list:
        if type(records) == pd.DataFrame:
            records = records["URL"]

        urls = list(
            "%s/%s/%s" % (
                self.url,
                endpoint,
                record.split("Record/", 1)[-1].split("/", 1)[0]
                )
            for record in records
        )

        responses = process_map(
            partial(self.__call__, interval=interval, max_retries=max_retries),
            urls,
            ascii=True,
            chunksize=1,
            desc="Requisitando detalhes dos registros",
            max_workers=max_workers,
            total=len(urls),
        )

        if parsed:
            return pd.concat(self._pd_records(r).T for r in responses)

        return responses

    def get_pdfs(
        self,
        df: pd.DataFrame,
        interval: int = INTERVAL,
        max_retries: int = MAX_RETRIES,
        max_workers: int = MAX_WORKERS,
        output_folder: str = ".",
    ) -> pd.DataFrame:
        tuples = [
            (x, y)
            for x, y in zip(
                [_.split("/")[-1] for _ in df["URL"]],
                df["URL (Texto)"],
            )
        ]

        pdfs = process_map(
            partial(self._get_pdfs, interval=interval, max_retries=max_retries, output_folder=output_folder),
            tuples,
            ascii=True,
            chunksize=1,
            desc="Requisitando arquivos PDF",
            max_workers=max_workers,
            total=len(tuples),
        )

        dict_pdfs = {}
        list(dict_pdfs.update(pdf) for pdf in pdfs)
        return pd.Series(dict_pdfs).to_frame(name="PDF")

    @staticmethod
    def _get_max_search_pages(response) -> int:
        return int(
            bs(response.content, "html.parser")
            .find("ul", {"class": "pagination"})
            .find_all("a")[-1]
            .attrs["href"]
            .split("page=")[-1]
        )

    def _get_pdfs(
        self,
        pair,
        interval: int = INTERVAL,
        max_retries: int = MAX_RETRIES,
        timeout: int = TIMEOUT,
        output_folder: str = ".",
    ):
        pdfs = {}
        index, url = pair
        errors = 0

        try:
            response = self.__call__(
                url,
                interval=interval,
                max_retries=max_retries,
                timeout=timeout
            )

            hyperlinks = self._get_hyperlinks(
                content=response.content,
                url=response.url
            )

            for i, pdf in enumerate(hyperlinks):
                try:
                    response = self.__call__(pdf, interval=interval, max_retries=max_retries)
                    if int(response.status_code) == 200 and response.content is not None:
                        with open(os.path.join(output_folder, f"{index}_{i}.pdf"), "wb") as pdf:
                            pdf.write(response.content)
                        try:
                            pdfs[index].append(f"{index}_{i}.pdf")
                        except:
                            pdfs[index] = [f"{index}_{i}.pdf"]
                except Exception as e:
                    log.warning(f"[ERROR] {e}: {pdf}")
                    errors += 1

        except Exception as e:
            log.warning(f"[ERROR] {e}: {url}")
            errors += 1

        return pdfs

    @staticmethod
    def _get_hyperlinks(content, url):
        return [
            "%s%s" % ((("http://" + urlparse(url).netloc) if h.startswith("/") else ""), h)
            for h in [
                h.attrs.get("href") or ""
                for h in bs(content, "html.parser").find_all("a")
            ]
            if ".pdf" in h.lower()
        ]

    @staticmethod
    def _pd_search(response) -> pd.DataFrame:
        return pd.DataFrame([{
            "Tipo":
                d.find_next("span", {"class": "format2"}).text,
            "Título":
                d.find_next("a", {"class": "title getFull"}).text.strip(),
            "Autoria":
                d.find_next("div", {"id": "rowAutor"}).select("div")[0].text.strip().split("     ")[-1].strip(),
            "Data de defesa":
                d.find_next("div", {"id": "datePublish"}).text.strip().split("Data de Defesa")[-1],
            "URL":
                "https://bdtd.ibict.br%s" % d.find_next("a", {"class": "title getFull"}).attrs["href"],
            "URL (Autoria)":
                "https://bdtd.ibict.br%s" % d.find_next("div", {"id": "rowAutor"}).select("div")[0].contents[1].attrs["href"],
            "URL (Texto)":
                d.find_next("a", {"class": "fulltext"}).attrs["href"],
            }
            for d in bs(
                response.content,
                "html.parser", # "lxml',
            )\
            .find_all(
                "div",
                {"class": "media"}
            )
        ])


    def _pd_records(self, response, decode="UTF-8") -> pd.DataFrame:
        return pd.concat([
                *list(
                    pd.Series({
                        "Título":
                            d.find("h3", {"property": "name"}).text.strip(),
                        "Resumo":
                            d.find("div", class_="col-sm-12").find("p").text if d.find("div", class_="col-sm-12").find("p") else "Resumo não disponível.",
                        "Descrição":
                            d.select("table", {"summary": "description"})[-1].text.strip()
                        }
                    )
                    for d in
                        bs(response.content, "html.parser")\
                        .find_all(
                            "div",
                            {"class": "mainbody right"}
                        )
                ),
                self.__series(
                    pd.read_html(
                        response.content.decode(decode)
                    )[0]
                ),
                # (
                #     self.__series(
                #         pd.read_html(
                #             bs(response.content, "html.parser").select("table", {"summary": "description"})[-1].decode(decode)
                #         )[0]
                #     )
                #     if not
                #         bs(response.content, "html.parser").select("table", {"summary": "description"})[-1].text.strip().startswith("Descrição não disponível")
                #     else
                #         pd.Series(dtype="object")
                # ),
        ])\
        .to_frame(name=response.url.split("/")[-1])

    @staticmethod
    def __series(df, index_pos=0) -> pd.Series:
        """ Returns a Pandas Series from DataFrame. """
        if df.shape[1] == 2:
            df.index = [x.rstrip(":") for x in df.iloc[:, index_pos]]
            return df.iloc[:, -1]
        return df

    '''
    @staticmethod
    def __dump(response, output_name: str, decode: str = "UTF-8"):
        """ Writes response content to JSON file. """
        with open(output_name, "w") as j:
            json.dump(response.content.decode(decode), j)
    '''


def getargs(args=argv[1:]) -> dict:
    parser = ArgumentParser()

    parser.add_argument("search_term",
                        action="store",
                        help="Termo a ser pesquisado na BDTD")

    parser.add_argument("-o", "--output-folder",
                        action="store",
                        help="Nome da pasta de saída (opcional)")

    parser.add_argument("-p", "--pages",
                        action="store",
                        default=None,
                        dest="max_pages",
                        type=int,
                        help=f"Número de páginas a serem consideradas durante busca (padrão: sem limite)")

    parser.add_argument("-t", "--type",
                        action="store",
                        default="AllFields",
                        help=f"Filtro a ser utilizado para busca por palavra-chave (padrão: 'AllFields')")

    parser.add_argument("-w", "--workers",
                        action="store",
                        default=MAX_WORKERS,
                        dest="max_workers",
                        type=int,
                        help=f"Número de tarefas a ser desempenhadas em coocorrência (padrão: {MAX_WORKERS})")

    parser.add_argument("--csv", "--no-excel",
                        action="store_false",
                        dest="excel",
                        help=f"Escreve arquivos de saída em formato CSV (padrão: Excel)")

    parser.add_argument("--interval",
                        action="store",
                        default=INTERVAL,
                        type=int,
                        help=f"Intervalo em segundos entre requisições (padrão: {INTERVAL})")

    parser.add_argument("--no-details",
                        action="store_false",
                        dest="get_details",
                        help="Desativa requisição de detalhes das publicações")

    parser.add_argument("--no-pdfs",
                        action="store_false",
                        dest="get_pdfs",
                        help="Desativa requisição dos arquivos em formato PDF")

    parser.add_argument("--retries",
                        action="store",
                        default=MAX_RETRIES,
                        dest="max_retries",
                        type=int,
                        help=f"Número de tentativas antes de abortar pesquisa (padrão: {MAX_RETRIES})")

    parser.add_argument("--timeout",
                        action="store",
                        default=TIMEOUT,
                        type=int,
                        help=f"Número de segundos antes de abortar requisição (padrão: {TIMEOUT})")

    args = parser.parse_args(args)
    return vars(args)


def main(excel: bool = True, get_details: bool = True, get_pdfs: bool = True, **kwargs) -> pd.DataFrame:
    bdtd = BDTD()

    search_term = kwargs.pop("search_term")
    output_folder = kwargs.pop("output_folder", ".")

    if not output_folder:
        output_folder = "BDTD (%s)" % search_term
    if not os.path.isdir(output_folder):
        os.mkdir(output_folder)

    df_search = bdtd.search(search_term, parsed=True, **kwargs)
    df_search.to_csv(os.path.join(output_folder, "data-search.csv"))

    if get_details:
        df_records = bdtd.get_records(
            df_search,
            interval=kwargs.get("interval"),
            max_retries=kwargs.get("max_retries"),
            max_workers=kwargs.get("max_workers"),
            parsed=True,
        )
        df_records.columns = [f"Detalhes_{x}" for x in df_records.columns]
        df_records.to_csv(os.path.join(output_folder, "data-records.csv"))

    if get_pdfs:
        output_pdf = os.path.join(output_folder, "pdf")
        if not os.path.isdir(output_pdf):
            os.mkdir(output_pdf)
        df_pdfs = bdtd.get_pdfs(
            df_search,
            interval=kwargs.get("interval"),
            max_retries=kwargs.get("max_retries"),
            max_workers=kwargs.get("max_workers"),
            output_folder=output_pdf,
        )
        df_pdfs.to_csv(os.path.join(output_folder, "data-pdfs.csv"))

    df = pd.concat([df_search, df_records, df_pdfs], axis=1).fillna("")
    getattr(df, "to_excel" if excel else "to_csv")(os.path.join(output_folder, "data.%s" % ("xlsx" if excel else "csv")))
    return df

if __name__ == "__main__":
    main(**getargs())
